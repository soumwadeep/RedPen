"""A deliberately small client for a local OpenAI-compatible endpoint.

Two properties matter here and both are enforced rather than assumed:
the base URL must be loopback (so no document can leave the machine), and
every call has a deterministic fallback, because a 1B model will occasionally
produce something unparseable -- the report must still be complete and correct.
"""

from __future__ import annotations

import json
import re
import urllib.parse
from dataclasses import dataclass

import httpx

from .config import assert_local


class EngineGone(RuntimeError):
    pass


@dataclass
class LocalLLM:
    base_url: str
    model: str = "local"
    temperature: float = 0.1
    timeout: float = 240.0

    def __post_init__(self) -> None:
        self.base_url = assert_local(self.base_url.rstrip("/"))

    # ------------------------------------------------------------------ api --
    def chat(self, system: str, user: str, max_tokens: int = 320,
             temperature: float | None = None, json_mode: bool = False) -> str:
        payload = {
            "model": self.model,
            "messages": [{"role": "system", "content": system},
                         {"role": "user", "content": user}],
            "max_tokens": max_tokens,
            "temperature": self.temperature if temperature is None else temperature,
            "top_p": 0.9,
        }
        if json_mode:
            payload["response_format"] = {"type": "json_object"}
            payload["temperature"] = 0.0
        try:
            r = httpx.post(f"{self.base_url}/chat/completions", json=payload,
                           timeout=self.timeout)
        except httpx.HTTPError as exc:
            raise EngineGone(f"local engine unreachable at {self.base_url}: {exc}") from exc
        if r.status_code != 200:
            raise EngineGone(f"engine returned {r.status_code}: {r.text[:200]}")
        data = r.json()
        try:
            return (data["choices"][0]["message"]["content"] or "").strip()
        except (KeyError, IndexError):
            return ""

    def stream(self, system: str, user: str, max_tokens: int = 600):
        payload = {
            "model": self.model,
            "messages": [{"role": "system", "content": system},
                         {"role": "user", "content": user}],
            "max_tokens": max_tokens, "temperature": self.temperature, "stream": True,
        }
        try:
            with httpx.stream("POST", f"{self.base_url}/chat/completions",
                              json=payload, timeout=self.timeout) as r:
                if r.status_code != 200:
                    raise EngineGone(f"engine returned {r.status_code}")
                for line in r.iter_lines():
                    if not line.startswith("data: "):
                        continue
                    chunk = line[6:]
                    if chunk.strip() == "[DONE]":
                        return
                    try:
                        d = json.loads(chunk)
                        delta = d["choices"][0]["delta"].get("content")
                    except (json.JSONDecodeError, KeyError, IndexError):
                        continue
                    if delta:
                        yield delta
        except httpx.HTTPError as exc:
            raise EngineGone(f"local engine unreachable: {exc}") from exc

    def ping(self) -> dict:
        try:
            r = httpx.get(f"{self.base_url}/models", timeout=2.0)
            names = [m.get("id") for m in r.json().get("data", [])]
            return {"ok": r.status_code == 200, "models": names, "base_url": self.base_url}
        except httpx.HTTPError as exc:
            return {"ok": False, "error": str(exc), "base_url": self.base_url}


# --------------------------------------------------------------------------- #
# Output hygiene for small models
# --------------------------------------------------------------------------- #

_PREAMBLE = re.compile(
    r"^(?:here(?:'|\u2019)s|below (?:is|are)|sure|certainly|of course|ok(?:ay)?|"
    r"certainly|absolutely|here is|i (?:can|will|would)|note to|note:)"
    r"[^.!\n]{0,90}[.!:\n]", re.I)
_BOLD_LABEL = re.compile(r"^\s*[\*\-_#]+\s*", re.S)


def strip_preamble(text: str) -> str:
    """A 1B instruct model loves saying "Here's a three-line explanation:".

    Small models open with meta-commentary, sometimes several lines of it, so
    this peels leading filler until it reaches something that is the answer.
    """
    text = text.strip()
    for _ in range(3):
        m = _PREAMBLE.match(text)
        if not m:
            break
        rest = text[m.end():].lstrip("\n ")
        if not rest:
            break
        text = rest
    return _BOLD_LABEL.sub("", text).strip()


def labelled(text: str, keys: list[str]) -> dict[str, str]:
    """Parse "RISK: ..." style output, tolerating markdown and case.

    Gemma writes `**RISK:**` as often as `RISK:`, and the colon can sit inside
    or outside the emphasis, so the label pattern allows decoration on both
    sides of it.
    """
    out = {k.lower(): "" for k in keys}
    text = strip_preamble(text)
    pattern = "|".join(re.escape(k) for k in keys)
    parts = re.split(
        rf"(?:^|\n)[ \t]*[*_#]{{0,2}}[ \t]*({pattern})"
        rf"[ \t]*[*_#]{{0,2}}[ \t]*[:\-)]?[ \t]*", text, flags=re.I)
    if len(parts) >= 3:
        for i in range(1, len(parts) - 1, 2):
            key = parts[i].lower().strip()
            if key in out:
                out[key] = parts[i + 1].strip().strip("*").strip()
    if all(not v for v in out.values()):
        out[keys[0].lower()] = text
    return out


def sentences(text: str, limit: int = 3) -> list[str]:
    text = strip_preamble(text)
    chunks = [c.strip() for c in re.split(r"(?<=[.!?])\s+", text) if c.strip()]
    out: list[str] = []
    for c in chunks:
        c = re.sub(r"^[\*\-\u2022# ]+", "", c).strip()
        if c:
            out.append(c)
        if len(out) >= limit:
            break
    return out


def bullets(text: str, limit: int = 5) -> list[str]:
    text = strip_preamble(text)
    lines = [l for l in text.split("\n")]
    out: list[str] = []
    for line in lines:
        s = re.sub(r"^\s*(?:[-*\u2022]|\d+[.)])\s*", "", line).strip()
        s = s.strip("*_").strip()
        if len(s) < 4:
            continue
        if re.match(r"^(here|note|overall)", s, re.I) and ":" in s and len(s.split(":")[0]) < 12:
            continue
        out.append(s)
        if len(out) >= limit:
            break
    return out


def parse_json(text: str):
    """Tolerant JSON extraction: fenced block, then first object/array."""
    text = strip_preamble(text)
    fence = re.search(r"```(?:json)?\s*(.+?)```", text, re.S)
    if fence:
        text = fence.group(1)
    for pat in (r"\{.*\}", r"\[.*\]"):
        m = re.search(pat, text, re.S)
        if m:
            try:
                return json.loads(m.group(0))
            except json.JSONDecodeError:
                continue
    return None
