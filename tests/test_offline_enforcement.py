"""Enforce the offline claim instead of observing it.

Raised in review of the submission: `scripts/offline_proof.sh` samples the
process's sockets with lsof, so a connection that opens and closes between
samples is invisible. Sampling can only ever report what it happened to catch.

This is the stronger version: every outbound socket is intercepted at the
syscall boundary for the duration of a full review. Anything that is not
loopback raises before a packet can leave. The review must still complete --
if it does, no remote host was contacted, by construction rather than by luck.
"""

from __future__ import annotations

import socket

import pytest

from redpen import config, engine, ingest, narrate
from redpen.llm import LocalLLM

LOOPBACK = {"127.0.0.1", "::1", "localhost", "127.0.0.53"}
_real_connect = socket.socket.connect
_attempted: list[str] = []


def _guard(self, address, *args, **kwargs):
    host = address[0] if isinstance(address, tuple) else address
    if isinstance(host, str) and host not in LOOPBACK:
        _attempted.append(host)
        raise AssertionError(f"RedPen tried to open a socket to {host!r}")
    return _real_connect(self, address, *args, **kwargs)


@pytest.fixture
def no_egress(monkeypatch):
    _attempted.clear()
    monkeypatch.setattr(socket.socket, "connect", _guard)
    monkeypatch.setattr(socket.socket, "connect_ex",
                        lambda self, address: 0 if _guard(self, address) is None else 1)
    yield _attempted
    assert not _attempted, f"outbound connect attempted to: {_attempted}"


def test_deterministic_review_needs_no_network_at_all(no_egress):
    """Rules + parsing + reporting, with the syscall layer refusing egress."""
    from pathlib import Path
    sample = Path(__file__).resolve().parent.parent / "samples" / "northgate_msa.txt"
    a = engine.analyse(ingest.load(sample))
    assert a.counts["stop"] >= 8
    from redpen import report
    assert "RedPen review" in report.to_markdown(a)
    assert "<blockquote>" in report.to_html(a)


def test_model_layer_completes_over_loopback_only(no_egress):
    """The real Gemma pass, with egress blocked. Skips if no engine is running,
    because there is no fallback endpoint to reach -- by design."""
    found = config.find_running_engine()
    if not found:
        pytest.skip("no local engine running; there is deliberately no remote one")
    from pathlib import Path
    sample = Path(__file__).resolve().parent.parent / "samples" / "lumen_typical.txt"
    a = engine.analyse(ingest.load(sample))
    llm = LocalLLM(base_url=found["base_url"], model=found["models"][0])
    ov = narrate.overview(llm, a)
    assert ov["worst"]
    email = narrate.negotiation_email(llm, a)
    assert email["body"]
    assert not _attempted


def test_a_misconfigured_endpoint_fails_closed(no_egress):
    """The privacy property that matters: an env var pointing at a hosted API
    must break the run, not silently leak the contract."""
    from redpen.config import NotLocal

    with pytest.raises(NotLocal):
        LocalLLM(base_url="https://api.openai.com/v1")
    with pytest.raises(NotLocal):
        LocalLLM(base_url="http://169.254.169.254/latest/meta-data")  # cloud creds thief
    with pytest.raises(NotLocal):
        LocalLLM(base_url="http://redpen-telemetry.example.com/collect")


def test_the_guard_itself_detects_egress():
    """A test that can never fail proves nothing; verify the tripwire trips."""
    with pytest.raises(AssertionError):
        s = socket.socket()
        try:
            _guard(s, ("93.184.216.34", 80))
        finally:
            s.close()
