"""Runtime configuration: engine discovery and the local model registry.

RedPen never talks to a remote host. ``resolve_base_url`` refuses any endpoint
that is not loopback, so a misconfigured environment variable cannot quietly
turn a privacy product into an uploader -- there is a test for exactly that.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import time
import urllib.parse
import urllib.request
from dataclasses import dataclass, asdict
from pathlib import Path

HOME = Path(os.environ.get("REDPEN_HOME", Path.home() / ".redpen"))
MODELS = HOME / "models"
SETTINGS = HOME / "settings.json"

APP_PORT = int(os.environ.get("REDPEN_PORT", "8790"))
ENGINE_PORT = int(os.environ.get("REDPEN_ENGINE_PORT", "8777"))

# Candidates we will probe, in preference order. All loopback.
ENDPOINTS = [
    f"http://127.0.0.1:{ENGINE_PORT}/v1",      # llama-server started by run.sh
    "http://127.0.0.1:8080/v1",                 # llama-server default
    "http://127.0.0.1:1234/v1",                 # LM Studio
    "http://127.0.0.1:11434/v1",                # Ollama's OpenAI shim
]

LOOPBACK = {"127.0.0.1", "localhost", "::1", "[::1]"}


class NotLocal(Exception):
    """Raised when a configured endpoint is not loopback."""


def assert_local(base_url: str) -> str:
    host = (urllib.parse.urlparse(base_url).hostname or "").lower()
    if host not in LOOPBACK:
        raise NotLocal(
            f"Refusing to use {base_url!r}: RedPen only speaks to a model "
            "running on this machine. Point REDPEN_BASE_URL at 127.0.0.1."
        )
    return base_url


@dataclass
class ModelSpec:
    key: str
    label: str
    filename: str
    hf_url: str
    sha_hint: str = ""
    params: str = ""

    @property
    def path(self) -> Path:
        return MODELS / self.filename

    @property
    def present(self) -> bool:
        return self.path.exists() and self.path.stat().st_size > 10_000_000


# Gemma is the default: small enough for an 8 GB laptop, open weights, and it
# ships a chat template llama.cpp understands. Qwen is the swap target that
# proves model-independence -- same rules, same report, different narration.
MODELS_AVAILABLE = {
    "gemma-3-1b": ModelSpec(
        key="gemma-3-1b",
        label="Gemma 3 1B (instruct)",
        filename="gemma-3-1b-it-Q4_K_M.gguf",
        hf_url="https://huggingface.co/ggml-org/gemma-3-1b-it-GGUF/resolve/main/gemma-3-1b-it-Q4_K_M.gguf",
        params="1B · Q4_K_M · 769 MB",
    ),
    "qwen-2.5-1.5b": ModelSpec(
        key="qwen-2.5-1.5b",
        label="Qwen 2.5 1.5B (instruct)",
        filename="qwen2.5-1.5b-instruct-q4_k_m.gguf",
        hf_url="https://huggingface.co/Qwen/Qwen2.5-1.5B-Instruct-GGUF/resolve/main/qwen2.5-1.5b-instruct-q4_k_m.gguf",
        params="1.5B · Q4_K_M · ~1.1 GB",
    ),
}

DEFAULT_MODEL = os.environ.get("REDPEN_MODEL", "gemma-3-1b")


# --------------------------------------------------------------------------- #
# Settings file
# --------------------------------------------------------------------------- #

def load_settings() -> dict:
    if SETTINGS.exists():
        try:
            return json.loads(SETTINGS.read_text())
        except json.JSONDecodeError:
            pass
    return {"model": DEFAULT_MODEL, "ctx": 8192, "threads": None}


def save_settings(patch: dict) -> dict:
    data = {**load_settings(), **patch}
    HOME.mkdir(parents=True, exist_ok=True)
    SETTINGS.write_text(json.dumps(data, indent=2) + "\n")
    return data


def active_model() -> ModelSpec:
    key = load_settings().get("model", DEFAULT_MODEL)
    return MODELS_AVAILABLE.get(key, MODELS_AVAILABLE[DEFAULT_MODEL])


# --------------------------------------------------------------------------- #
# Model download
# --------------------------------------------------------------------------- #

def ensure_weights(spec: ModelSpec, quiet: bool = False) -> Path:
    """Download GGUF weights if absent. One-time, ~770 MB, from Hugging Face."""
    if spec.present:
        return spec.path
    MODELS.mkdir(parents=True, exist_ok=True)
    tmp = spec.path.with_suffix(".gguf.part")
    if not quiet:
        print(f"↓ downloading {spec.label} ({spec.params}) → {spec.path}")
    if shutil.which("curl"):
        cmd = ["curl", "-fL", "--retry", "3", "-C", "-", "-o", str(tmp), spec.hf_url]
        subprocess.run(cmd, check=True)
    else:
        with urllib.request.urlopen(spec.hf_url) as r, open(tmp, "wb") as f:
            shutil.copyfileobj(r, f, 1024 * 256)
    tmp.replace(spec.path)
    return spec.path


# --------------------------------------------------------------------------- #
# Engine
# --------------------------------------------------------------------------- #

def probe(base_url: str, timeout: float = 1.2) -> dict | None:
    try:
        with urllib.request.urlopen(assert_local(base_url) + "/models", timeout=timeout) as r:
            data = json.loads(r.read())
    except Exception:
        return None
    names = [m.get("id") or m.get("name") or "" for m in data.get("data", [])]
    return {"base_url": base_url, "models": [n for n in names if n]}


def find_running_engine(prefer: str | None = None) -> dict | None:
    """Return the first live local endpoint, preferring one already holding a
    Gemma (or the requested model) so `redpen` works with LM Studio or Ollama."""
    hits = [p for p in (probe(u) for u in ENDPOINTS) if p]
    if not hits:
        env = os.environ.get("REDPEN_BASE_URL")
        if env:
            hits = [p for p in (probe(env),) if p]
    if not hits:
        return None
    want = (prefer or active_model().label).split()[0].lower()
    for hit in hits:
        if any(want in m.lower() for m in hit["models"]):
            return hit
    return hits[0]


def engine_binary() -> str | None:
    return shutil.which("llama-server") or shutil.which("/opt/homebrew/bin/llama-server")


def start_engine(spec: ModelSpec | None = None, port: int = ENGINE_PORT,
                 ctx: int | None = None, quiet: bool = False) -> dict:
    """Launch llama-server on loopback with the chosen weights."""
    spec = spec or active_model()
    binary = engine_binary()
    if not binary:
        raise RuntimeError(
            "llama-server not found. Install llama.cpp (brew install llama.cpp, "
            "or a release binary on your PATH), or run LM Studio / Ollama and "
            "set REDPEN_BASE_URL to its loopback /v1 address."
        )
    path = ensure_weights(spec, quiet=quiet)
    threads = load_settings().get("threads") or os.cpu_count()
    cmd = [
        binary, "-m", str(path), "--alias", spec.key,
        "--ctx-size", str(ctx or load_settings().get("ctx", 8192)),
        "--n-gpu-layers", "99", "--threads", str(max(2, min(threads or 4, 4))),
        "--host", "127.0.0.1", "--port", str(port), "--jinja", "--no-webui",
    ]
    log = (HOME / "engine.log")
    HOME.mkdir(parents=True, exist_ok=True)
    if not quiet:
        print("• starting local engine: " + " ".join(cmd[1:3]))
    handle = open(log, "ab")
    proc = subprocess.Popen(cmd, stdout=handle, stderr=handle, start_new_session=True)
    base = f"http://127.0.0.1:{port}/v1"
    deadline = time.time() + 120
    while time.time() < deadline:
        hit = probe(base)
        if hit:
            hit["pid"] = proc.pid
            return hit
        if proc.poll() is not None:
            raise RuntimeError(f"engine exited early -- see {log}")
        time.sleep(0.5)
    raise RuntimeError(f"engine did not become ready on {base} -- see {log}")


def state() -> dict:
    spec = active_model()
    engine = find_running_engine()
    return {
        "model": asdict(spec) | {"present": spec.present, "path": str(spec.path)},
        "models": [asdict(m) | {"present": m.present} for m in MODELS_AVAILABLE.values()],
        "engine": engine,
        "offline_ready": bool(engine),
        "settings": load_settings(),
        "home": str(HOME),
    }
