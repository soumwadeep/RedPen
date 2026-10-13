"""The HTTP surface, exports, and the privacy claims the product makes.

These exist because the first version of the API returned 500 while every unit
test stayed green: to_dict() was only ever reached through the server. So the
transport layer gets tested like the logic does.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from redpen import report, server
from redpen.ingest import load

SAMPLES = Path(__file__).resolve().parent.parent / "samples"
WEB = Path(__file__).resolve().parent.parent / "web"

client = TestClient(server.app)


@pytest.fixture()
def reviewed():
    """Function-scoped on purpose: the cache holds 8 reviews, so a shared token
    can be legitimately evicted by another test. That is the product working as
    designed, not a bug -- the export path gets a fresh one."""
    r = client.post("/api/sample/lumen_typical")
    assert r.status_code == 200, r.text
    return r.json()


# --------------------------------------------------------------------------- #
# Transport
# --------------------------------------------------------------------------- #

def test_index_is_served():
    r = client.get("/")
    assert r.status_code == 200
    assert "REDPEN" in r.text
    assert "DROP CONTRACT" in r.text


def test_status_reports_privacy(reviewed):
    st = client.get("/api/status").json()
    assert st["privacy"]["binds"] == "127.0.0.1"
    assert st["cache"]["written_to_disk"] == 0
    assert st["rules"]["builtin"] >= 30
    assert st["model"]["present"] is True


def test_doctor_runs(reviewed):
    d = client.get("/api/doctor").json()
    assert d["rules"]["builtin"] >= 30
    assert d["ram_gb"] > 0


def test_review_returns_full_json(reviewed):
    assert reviewed["score"] > 0 and reviewed["band"]
    assert reviewed["token"]
    assert reviewed["document"]["clauses"] >= 5
    assert reviewed["engine"]["offline"] is True
    for f in reviewed["findings"]:
        assert f["band"] in {"stop", "fix", "ask", "note"}
        assert f["presence"] in {"present", "missing", "refused"}
        assert f["why"] and f["fix"] and f["ask"]
        for e in f["evidence"]:
            assert e["page"] >= 1 and e["quote"]


def test_pasted_text_is_reviewed():
    text = (SAMPLES / "northgate_msa.txt").read_text()
    fd = {"text": text}
    r = client.post("/api/review", data=fd)
    assert r.status_code == 200
    body = r.json()
    assert body["counts"]["stop"] >= 6
    assert "pasted" in body["document"]["source"]


def test_pdf_upload_is_reviewed_without_touching_disk():
    data = (SAMPLES / "northgate_msa.pdf").read_bytes()
    r = client.post("/api/review", files={"file": ("secret_contract.pdf", data, "application/pdf")})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["document"]["pages"] >= 2
    assert body["document"]["name"] == "secret_contract"
    # the name the user uploaded with must not be persisted anywhere
    assert not list(Path.cwd().glob("secret_contract*"))


def test_rejects_garbage():
    r = client.post("/api/review", data={"text": "too short to be a contract"})
    assert r.status_code == 422
    r = client.post("/api/sample/does_not_exist")
    assert r.status_code == 404
    r = client.get("/api/report/not-a-token")
    assert r.status_code == 404


def test_cache_is_bounded():
    for i in range(12):
        client.post("/api/sample/lumen_typical")
    assert len(server._CACHE) <= server.CACHE_LIMIT


# --------------------------------------------------------------------------- #
# Exports
# --------------------------------------------------------------------------- #

def test_markdown_export(reviewed):
    md = client.get(f"/api/export/{reviewed['token']}?fmt=md").text
    assert md.startswith("# RedPen review")
    assert "Risk score" in md
    assert "not a lawyer" in md
    assert "Ask for." in md


def test_html_brief_is_self_contained(reviewed):
    html = client.get(f"/api/export/{reviewed['token']}?fmt=html").text
    assert "<blockquote>" in html
    assert "VERBATIM" in html
    # a brief the user emails to a friend must not phone home
    for bad in re.findall(r'(?:src|href)="([^"]+)"', html):
        assert not bad.startswith(("http://", "https://", "//")), f"remote asset {bad}"


def test_json_export_round_trips(reviewed):
    body = json.loads(client.get(f"/api/export/{reviewed['token']}?fmt=json").text)
    assert body["analysis"]["score"] == reviewed["score"]
    assert len(body["analysis"]["findings"]) == len(reviewed["findings"])


def test_email_export_falls_back_to_template(reviewed):
    """No narration has run yet, and the user still gets a usable email."""
    body = client.get(f"/api/export/{reviewed['token']}?fmt=email").text
    assert "Suggested:" in body and "before I sign" in body


# --------------------------------------------------------------------------- #
# Model layer
# --------------------------------------------------------------------------- #

def test_narration_stream_is_sse_and_degrades_gracefully(monkeypatch):
    """With no engine the stream must still deliver a complete email."""
    monkeypatch.setattr(server.config, "find_running_engine", lambda prefer=None: None)
    tok = client.post("/api/sample/northgate_msa").json()["token"]
    with client.stream("GET", f"/api/narrate/{tok}") as r:
        assert r.status_code == 200
        assert "text/event-stream" in r.headers["content-type"]
        raw = "".join(iter_lines(r))
    events = dict(event_types(raw))
    assert "email" in events and "done" in events
    assert "template" in raw


def event_types(raw: str):
    current = None
    for line in raw.split("\n"):
        if line.startswith("event: "):
            current = line[7:].strip()
        elif line.startswith("data: ") and current:
            yield current, line[6:]
            current = None


def iter_lines(response):
    for chunk in response.iter_text():
        yield chunk


@pytest.mark.slow
def test_full_model_layer_produces_gemma_output():
    """Real Gemma pass: skip when no local engine is running."""
    found = server.config.find_running_engine()
    if not found:
        pytest.skip("no local engine -- start llama-server or run `redpen`")
    tok = client.post("/api/sample/lumen_typical").json()["token"]
    raw = client.get(f"/api/narrate/{tok}").text
    got = dict(event_types(raw))
    ov = json.loads(got["overview"][-1])
    assert ov["source"] in {"gemma", "library"}
    email = json.loads(got["email"][-1])
    assert email["source"] == "gemma", "Gemma should clear the faithfulness check"
    assert "[your name]" in email["body"] or "your name" in email["body"].lower()
    amb = json.loads(got["ambiguity"][-1])["items"]
    numbers = {c["number"] for c in server._CACHE[tok]["analysis"]["contract"].clauses}
    for item in amb:
        assert item["clause"] in numbers, "model cited a clause that does not exist"


# --------------------------------------------------------------------------- #
# Privacy claims made to the user
# --------------------------------------------------------------------------- #

def test_llm_refuses_a_remote_endpoint():
    from redpen.config import NotLocal
    from redpen.llm import LocalLLM

    for url in ["https://api.openai.com/v1", "http://example.com:8000/v1",
                "https://127.0.0.1.evil.test/v1"]:
        with pytest.raises(NotLocal):
            LocalLLM(base_url=url)


def test_loopback_endpoints_are_allowed():
    from redpen.llm import LocalLLM

    for url in ["http://127.0.0.1:8777/v1", "http://localhost:11434/v1"]:
        assert LocalLLM(base_url=url).base_url.startswith("http://")


def test_ui_makes_no_remote_requests():
    html = (WEB / "index.html").read_text()
    for bad in re.findall(r'(?:src|href)="(https?://[^"]+)"', html):
        pytest.fail(f"the page fetches {bad} -- breaks the offline promise")
    assert "fonts.googleapis" not in html
    assert "analytics" not in html.lower()


def test_no_document_content_is_written_by_the_pipeline(tmp_path, monkeypatch):
    """Reviewing a contract must leave no artefact behind unless asked."""
    monkeypatch.chdir(tmp_path)
    data = (SAMPLES / "northgate_msa.pdf").read_bytes()
    client.post("/api/review", files={"file": ("client_matter.pdf", data, "application/pdf")})
    assert list(tmp_path.iterdir()) == []


def test_terminal_and_markdown_agree_on_findings():
    a = load(SAMPLES / "lumen_typical.txt")
    from redpen.engine import analyse

    an = analyse(a)
    md = report.to_markdown(an)
    for f in an.findings[:5]:
        assert f["title"] if isinstance(f, dict) else f.title in md
