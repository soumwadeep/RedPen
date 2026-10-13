"""The local web app: FastAPI on loopback, in-memory only.

Three rules the code enforces rather than merely intends:

  1. Uploads are parsed from bytes and never written to disk.
  2. Analyses live in a bounded in-memory cache; nothing is persisted.
  3. The only HTTP client in the project (redpen.llm.LocalLLM) refuses a base
     URL that is not loopback, so no request can leave the machine.

Findings are returned immediately because the deterministic engine takes
milliseconds; the model layer is streamed afterwards so the interface never
sits on a spinner waiting for a 1B model to write an email.
"""

from __future__ import annotations

import json
import secrets
import time
from collections import OrderedDict
from pathlib import Path

from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.responses import HTMLResponse, JSONResponse, PlainTextResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles

from . import __version__, config, engine, ingest, narrate, report
from .llm import LocalLLM

WEB = Path(__file__).resolve().parent.parent / "web"
SAMPLES = Path(__file__).resolve().parent.parent / "samples"
CACHE_LIMIT = 8

app = FastAPI(title="RedPen", version=__version__,
              description="Offline contract review. Loopback only.")

# token -> {"analysis": Analysis, "narration": dict|None, "ts": float}
_CACHE: "OrderedDict[str, dict]" = OrderedDict()
_last_error: dict = {}


def _put(analysis: engine.Analysis) -> str:
    token = secrets.token_urlsafe(8)
    _CACHE[token] = {"analysis": analysis, "narration": None, "ts": time.time()}
    while len(_CACHE) > CACHE_LIMIT:
        _CACHE.popitem(last=False)
    return token


def _get(token: str) -> dict:
    entry = _CACHE.get(token)
    if not entry:
        raise HTTPException(404, "That review is no longer in memory. RedPen keeps "
                                 "the last 8 and never writes them to disk.")
    _CACHE.move_to_end(token)
    return entry


def _llm_or_none() -> LocalLLM | None:
    found = config.find_running_engine()
    if not found:
        return None
    return LocalLLM(base_url=found["base_url"], model=(found["models"] or ["local"])[0])


# --------------------------------------------------------------------------- #
# Review
# --------------------------------------------------------------------------- #

@app.post("/api/review")
async def review(file: UploadFile | None = File(None), text: str | None = Form(None),
                 name: str | None = Form(None)) -> JSONResponse:
    t0 = time.time()
    try:
        if file is not None and file.filename:
            data = await file.read()
            if len(data) > 12_000_000:
                raise HTTPException(413, "That file is over 12 MB. RedPen works on "
                                         "the agreement, not its attachments.")
            contract = ingest.load_bytes(file.filename or "uploaded agreement", data)
        elif text and text.strip():
            contract = ingest.load_text(name or "pasted agreement", text)
        else:
            raise HTTPException(422, "Send a file or paste the agreement text.")
    except ingest.DocumentTooShort as exc:
        raise HTTPException(422, str(exc))
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(400, f"Could not read that document: {exc}")

    analysis = engine.analyse(contract)
    token = _put(analysis)
    payload = analysis.to_dict()
    payload["token"] = token
    payload["ms"] = round((time.time() - t0) * 1000)
    payload["engine"] = _engine_line()
    return JSONResponse(payload)


@app.post("/api/sample/{name}")
def sample(name: str) -> JSONResponse:
    path = (SAMPLES / f"{name}.pdf")
    if not path.exists():
        path = SAMPLES / f"{name}.txt"
    if not path.exists():
        raise HTTPException(404, f"no sample called {name!r}")
    contract = ingest.load(path)
    analysis = engine.analyse(contract)
    token = _put(analysis)
    payload = analysis.to_dict()
    payload["token"] = token
    payload["engine"] = _engine_line()
    return JSONResponse(payload)


@app.get("/api/samples")
def samples() -> list[dict]:
    out = []
    for p in sorted(SAMPLES.glob("*.txt")):
        try:
            a = engine.analyse(ingest.load(p))
            out.append({"name": p.stem, "score": a.score, "band": a.band,
                        "clauses": a.contract.clause_count, "findings": len(a.findings),
                        "stops": a.counts["stop"]})
        except Exception as exc:
            _last_error.clear(); _last_error[p.stem] = str(exc)
    return out


def _engine_line() -> dict:
    found = config.find_running_engine()
    spec = config.active_model()
    return {"base_url": found["base_url"] if found else None,
            "model": (found["models"][0] if found and found["models"] else spec.key),
            "loaded": bool(found), "weights_on_disk": spec.present,
            "offline": True}


# --------------------------------------------------------------------------- #
# Model layer, streamed
# --------------------------------------------------------------------------- #

def _sse(event: str, data: dict) -> str:
    return f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"


@app.get("/api/narrate/{token}")
def narrate_stream(token: str):
    """Server-sent events: overview, then one explanation per top finding, then
    the email, then ambiguities. Each event lands as it is produced."""

    def generate():
        entry = _CACHE.get(token)
        if not entry:
            yield _sse("error", {"message": "review expired from memory"})
            return
        a: engine.Analysis = entry["analysis"]
        llm = _llm_or_none()
        if llm is None:
            yield _sse("status", {"model": False,
                                  "note": "no local engine -- showing library wording only"})
            yield _sse("email", {"body": narrate.email_fallback(a), "source": "template"})
            yield _sse("done", {})
            return
        yield _sse("status", {"model": llm.model, "base_url": llm.base_url})
        narration: dict = {}
        t0 = time.time()
        narration["overview"] = narrate.overview(llm, a)
        yield _sse("overview", narration["overview"])
        notes = {}
        for f in a.findings[: narrate.MAX_EXPLAIN]:
            notes[f.rid] = narrate.explain(llm, a, f)
            yield _sse("explain", {"rid": f.rid, "text": notes[f.rid]})
        narration["explain"] = notes
        em = narrate.negotiation_email(llm, a)
        narration["email"] = em
        yield _sse("email", em)
        amb = narrate.ambiguities(llm, a)
        narration["ambiguity"] = amb
        yield _sse("ambiguity", {"items": amb})
        entry["narration"] = narration
        yield _sse("done", {"seconds": round(time.time() - t0, 1)})

    return StreamingResponse(generate(), media_type="text/event-stream",
                             headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})


# --------------------------------------------------------------------------- #
# Exports
# --------------------------------------------------------------------------- #

@app.get("/api/report/{token}")
def get_report(token: str) -> dict:
    entry = _get(token)
    return {"analysis": entry["analysis"].to_dict(),
            "narration": entry["narration"],
            "model": _engine_line()}


@app.get("/api/export/{token}")
def export(token: str, fmt: str = "md") -> PlainTextResponse:
    entry = _get(token)
    a, n = entry["analysis"], entry["narration"]
    if fmt == "html":
        return HTMLResponse(report.to_html(a, n),
                            headers={"Content-Disposition": f'attachment; filename="redpen-{a.contract.name}.html"'})
    if fmt == "json":
        return PlainTextResponse(json.dumps({"analysis": a.to_dict(), "narration": n},
                                            ensure_ascii=False, indent=2),
                                 media_type="application/json")
    if fmt == "email":
        body = (n or {}).get("email", {}).get("body") or narrate.email_fallback(a)
        return PlainTextResponse(body)
    return PlainTextResponse(report.to_markdown(a, n))


# --------------------------------------------------------------------------- #
# Status and model choice
# --------------------------------------------------------------------------- #

@app.get("/api/status")
def status() -> dict:
    from .rules import RULES, load_user_rules

    st = config.state()
    st["cache"] = {"reviews_in_memory": len(_CACHE), "written_to_disk": 0}
    st["rules"] = {"builtin": len(RULES), "user": len(load_user_rules()),
                   "editable": str(config.HOME / "rules")}
    st["privacy"] = {
        "binds": "127.0.0.1",
        "outbound_requests": "none -- LocalLLM raises if a base URL is not loopback",
        "model_weights": f"{config.active_model().filename} in {config.MODELS}",
        "telemetry": "none, no analytics script in the page",
    }
    return st


@app.post("/api/model")
def choose_model(body: dict) -> dict:
    key = (body or {}).get("model")
    if key not in config.MODELS_AVAILABLE:
        raise HTTPException(422, f"unknown model {key!r}")
    config.save_settings({"model": key})
    spec = config.MODELS_AVAILABLE[key]
    try:
        if not spec.present:
            config.ensure_weights(spec, quiet=True)
        found = config.start_engine(spec, port=config.ENGINE_PORT)
        return {"ok": True, "model": key, "engine": found}
    except Exception as exc:
        return {"ok": False, "model": key, "error": str(exc)}


@app.get("/api/doctor")
def doctor() -> dict:
    import subprocess

    out: dict = {"version": __version__}
    out["ram_gb"] = round(
        int(subprocess.run(["sysctl", "-n", "hw.memsize"], capture_output=True,
                           text=True).stdout or 0) / 1024 ** 3, 1)
    out["engine"] = _engine_line()
    llm = _llm_or_none()
    if llm:
        t0 = time.time()
        reply = llm.chat("Say ok.", "Reply: ok", max_tokens=6)
        out["latency_s"] = round(time.time() - t0, 2)
        out["reply"] = reply[:30]
    from .rules import RULES, load_user_rules

    out["rules"] = {"builtin": len(RULES), "user": len(load_user_rules())}
    out["models_dir"] = str(config.MODELS)
    return out


# --------------------------------------------------------------------------- #
# UI
# --------------------------------------------------------------------------- #

@app.get("/", response_class=HTMLResponse)
def index() -> str:
    page = WEB / "index.html"
    if not page.exists():
        return "<h1>RedPen</h1><p>web/index.html missing</p>"
    return page.read_text()


if WEB.exists():
    app.mount("/ui", StaticFiles(directory=str(WEB)), name="ui")
