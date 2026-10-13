"""The `redpen` command.

    redpen review contract.pdf            review with the local model
    redpen review contract.pdf --no-llm   deterministic pass only (instant)
    redpen                                start the app and open the browser
    redpen models                         list weights on disk / download one
    redpen doctor                         what would break, before it breaks
    redpen rules                          count and list the loaded rule library
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
import webbrowser
from pathlib import Path

from . import __version__, config, engine, ingest, narrate, report
from .llm import LocalLLM


def _llm(use_model: bool, quiet: bool = False) -> tuple[LocalLLM | None, str]:
    """Return a client, or None with a reason. Never reaches off-box."""
    if not use_model:
        return None, "deterministic only (--no-llm)"
    found = config.find_running_engine()
    if not found:
        if not quiet:
            print("· no local engine running -- starting one", flush=True)
        try:
            found = config.start_engine(quiet=quiet)
        except Exception as exc:
            return None, f"engine unavailable ({exc})"
    return LocalLLM(base_url=found["base_url"], model=(found["models"] or ["local"])[0]), None


# --------------------------------------------------------------------------- #

def cmd_review(args) -> int:
    paths = [Path(p) for p in args.files]
    for path in paths:
        t0 = time.time()
        try:
            contract = ingest.load(path)
        except (ingest.DocumentTooShort, FileNotFoundError, ValueError) as exc:
            print(f"✗ {path}: {exc}", file=sys.stderr)
            continue

        a = engine.analyse(contract)
        llm, degraded = _llm(not args.no_llm, quiet=args.quiet)
        narration = None
        if llm and not args.no_llm:
            if not args.quiet:
                print(f"· {args.tasks} with {llm.model} at {llm.base_url} "
                      f"(local, offline)", flush=True)
            narration = narrate.narrate(llm, a)
        dt = time.time() - t0

        if args.json:
            payload = a.to_dict()
            payload["narration"] = narration
            payload["model"] = llm.model if llm else None
            payload["degraded"] = degraded
            print(json.dumps(payload, ensure_ascii=False, indent=2))
        elif args.html:
            Path(args.html).write_text(report.to_html(a, narration))
            print(f"✓ {path.name} -> {args.html}  (score {a.score}/99, "
                  f"{len(a.findings)} findings, {dt:.1f}s)")
        else:
            print(report.to_terminal(a, narration))
            if degraded:
                print(f"  note: model layer skipped -- {degraded}")
            print(f"  {dt:.1f}s · engine {llm.base_url if llm else 'off'} · loopback only")
    return 0


def cmd_serve(args) -> int:
    llm, degraded = _llm(not args.no_llm, quiet=False)
    if degraded:
        print(f"! model layer off: {degraded}", file=sys.stderr)
        print("! the deterministic review still works -- open the UI anyway.",
              file=sys.stderr)
    url = f"http://127.0.0.1:{args.port}"
    print(f"▲ RedPen {__version__} serving {url}")
    print("  bound to loopback · no outbound requests · documents stay on this laptop")
    if args.open:
        threading_open(url)
    import uvicorn
    uvicorn.run("redpen.server:app", host="127.0.0.1", port=args.port,
                log_level="warning" if args.quiet else "info", reload=False)
    return 0


def threading_open(url: str) -> None:
    import threading
    threading.Timer(1.0, lambda: webbrowser.open(url)).start()


def cmd_models(args) -> int:
    st = config.state()
    print(f"home: {st['home']}")
    print(f"engine: {st['engine'] or 'not running (redpen starts it on demand)'}")
    for m in st["models"]:
        mark = "✓" if m["present"] else " "
        sel = "  <- active" if m["key"] == st["model"]["key"] else ""
        size = ""
        if m["present"]:
            size = f"  {Path(m['path']).stat().st_size / 1e6:.0f} MB"
        print(f"  [{mark}] {m['key']:<14} {m['label']:<30} {m['params']}{size}{sel}")
    if args.use:
        if args.use not in config.MODELS_AVAILABLE:
            print(f"unknown model {args.use!r}", file=sys.stderr)
            return 2
        config.save_settings({"model": args.use})
        config.ensure_weights(config.MODELS_AVAILABLE[args.use])
        print(f"· active model -> {args.use}. Restart redpen to load it.")
    if args.download:
        spec = config.MODELS_AVAILABLE.get(args.download)
        if not spec:
            print(f"unknown model {args.download!r}", file=sys.stderr)
            return 2
        config.ensure_weights(spec)
        print(f"✓ {spec.filename}")
    return 0


def cmd_rules(args) -> int:
    from .rules import RULES, all_rules, load_user_rules

    user = load_user_rules()
    print(f"{len(RULES)} built-in rules · {len(user)} user rules · "
          f"{len(all_rules())} effective")
    print(f"drop JSON files in {config.HOME / 'rules'} to add your own")
    if args.list:
        for r in sorted(RULES, key=lambda r: (-r.severity, r.category)):
            scope = "doc" if r.doc_scope else "clause"
            print(f"  [{r.severity}] {r.rid:<30} {r.category:<8} {scope:<6} {r.title}")
    return 0


def cmd_doctor(args) -> int:
    st = config.state()
    ok = True
    print(f"RedPen {__version__}")
    print(f"  home        {st['home']}")
    mem = _ram_gb()
    print(f"  ram         {mem:.1f} GB" + ("  (tight: use --no-llm or close apps)" if mem and mem < 7.5 else ""))
    spec = config.active_model()
    print(f"  model       {spec.key} {'✓ on disk' if spec.present else '✗ not downloaded yet'}")
    if not spec.present:
        ok = False
    eng = config.find_running_engine()
    print(f"  engine      {eng['base_url'] if eng else 'not running (started on demand)'}")
    if eng:
        llm = LocalLLM(base_url=eng["base_url"], model=(eng["models"] or ["local"])[0])
        print(f"  handshake   {llm.ping()}")
        t0 = time.time()
        out = llm.chat("Reply with one word.", "Say: ok", max_tokens=8)
        print(f"  inference   {time.time() - t0:.1f}s -> {out[:40]!r}")
    binary = config.engine_binary()
    print(f"  llama-server {binary or '✗ not on PATH (brew install llama.cpp)'}")
    if not binary:
        ok = False
    try:
        import pymupdf  # noqa: F401
        print("  pymupdf     ✓")
    except ImportError:
        print("  pymupdf     ✗ (pip install pymupdf)")
        ok = False
    print(f"  network     loopback-only by design; this run made no remote request")
    print("  verdict     " + ("ready" if ok else "needs the items marked ✗"))
    return 0 if ok else 1


def _ram_gb() -> float:
    try:
        raw = subprocess.run(["sysctl", "-n", "hw.memsize"], capture_output=True,
                             text=True, timeout=3).stdout.strip()
        return int(raw) / 1024 ** 3
    except Exception:
        return 0.0


# --------------------------------------------------------------------------- #

def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="redpen",
        description="Offline contract review for freelancers. Open weights, "
                    "open rules, nothing leaves the laptop.")
    p.add_argument("--version", action="version", version=f"redpen {__version__}")
    sub = p.add_subparsers(dest="cmd")

    r = sub.add_parser("review", help="review one or more contracts")
    r.add_argument("files", nargs="+")
    r.add_argument("--no-llm", action="store_true", help="deterministic pass only")
    r.add_argument("--json", action="store_true", help="machine-readable output")
    r.add_argument("--html", help="write a standalone HTML brief to this path")
    r.add_argument("--tasks", default="brief, findings, email")
    r.add_argument("-q", "--quiet", action="store_true")
    r.set_defaults(func=cmd_review)

    s = sub.add_parser("serve", help="run the local web app")
    s.add_argument("--port", type=int, default=config.APP_PORT)
    s.add_argument("--no-llm", action="store_true")
    s.add_argument("--no-open", dest="open", action="store_false", default=True)
    s.add_argument("-q", "--quiet", action="store_true")
    s.set_defaults(func=cmd_serve)

    m = sub.add_parser("models", help="show or change the local weights")
    m.add_argument("--use", help="set the active model key")
    m.add_argument("--download", help="fetch a model's weights now")
    m.set_defaults(func=cmd_models)

    ru = sub.add_parser("rules", help="show the red-flag library")
    ru.add_argument("--list", action="store_true")
    ru.set_defaults(func=cmd_rules)

    d = sub.add_parser("doctor", help="check this machine before a demo")
    d.set_defaults(func=cmd_doctor)
    return p


def main(argv: list[str] | None = None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    if not argv:
        argv = ["serve"]
    parser = build_parser()
    args = parser.parse_args(argv)
    if not getattr(args, "func", None):
        parser.print_help()
        return 0
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
