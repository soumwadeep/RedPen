"""Report rendering: terminal text, Markdown, and a standalone HTML brief.

The HTML is self-contained (no CDN, no fonts, no scripts fetched) because the
product's promise is that it works on a plane. A user should be able to email
the brief to a friend and nothing about the document leaks when it is opened.
"""

from __future__ import annotations

import html
import json
import re
from datetime import datetime

from .engine import Analysis

SEV_ICON = {3: "STOP", 2: "FIX", 1: "ASK", 0: "NOTE"}
SEV_COLOR = {3: "#ff5d5d", 2: "#ffb020", 1: "#5ad1ff", 0: "#8b93a7"}

BAND_COPY = {
    "high": "Do not sign this yet. Fix the items below first.",
    "medium": "Workable, but several terms should change before you start.",
    "low": "Mostly reasonable. A couple of asks are worth making.",
    "clean": "Nothing in the red-flag library matched. Still read it yourself.",
}


def _clause_of(a: Analysis, cid: str):
    return a.contract.clause(cid)


# --------------------------------------------------------------------------- #
# Markdown
# --------------------------------------------------------------------------- #

def to_markdown(a: Analysis, narration: dict | None = None) -> str:
    n = narration or {}
    d = a.contract
    out = [
        f"# RedPen review - {d.name}",
        "",
        f"- **Risk score:** {a.score}/99 ({a.band})",
        f"- **Document:** {d.pages} pages, {d.clause_count} clauses, "
        f"{len(d.text.split())} words",
        f"- **Findings:** {a.counts['stop']} stop, {a.counts['fix']} fix, "
        f"{a.counts['ask']} ask",
        f"- **Document type:** {a.doc_type.label}",
        f"- **Stated terms:** {_shape_text(a)}",
        f"- **Reviewed:** {datetime.now():%Y-%m-%d %H:%M} · offline, on this machine",
        "",
        f"> {BAND_COPY[a.band]}",
        "",
    ]
    if a.blanks.total:
        out += [f"**{a.blanks.total} unfilled fields** -- this is a draft, not a deal yet: "
                + ", ".join(f"[{f}]" for f in a.blanks.fields[:10]), ""]
    if not a.doc_type.contractual:
        out += ["This does not read as an agreement, so there is nothing to review. "
                "RedPen scores promises; an instruction list makes none.", ""]
    ov = n.get("overview")
    if ov:
        out += ["## What this agreement is", "",
                f"- Deal: {ov['deal']}", f"- Worst problem: {ov['worst']}",
                f"- First ask: {ov['first']}", ""]

    out += ["## Findings", ""]
    for i, f in enumerate(a.findings, 1):
        loc = ", ".join(f"{e.label} (p.{e.page})" for e in f.evidence) or "not in the agreement"
        out.append(f"### {i}. {f.title}  \n`{SEV_ICON[f.severity]}` · {f.category} · {loc}")
        if f.evidence:
            out.append("")
            for e in f.evidence[:2]:
                out.append(f"> {e.quote}")
        out.append("")
        out.append(f"**Why it matters.** {n.get('explain', {}).get(f.rid, f.why)}")
        out.append("")
        out.append(f"**Ask for.** {f.fix}")
        out.append("")
    amb = n.get("ambiguity") or []
    if amb:
        out += ["## Also unclear", ""]
        out += [f"- Clause {x['clause']}: {x['note']}" for x in amb]
        out.append("")
    em = n.get("email")
    if em:
        out += ["## Negotiation email", "", f"_({em['source']})_", "", "```",
                em["body"], "```", ""]
    out += ["---", "",
            "RedPen is a pattern-matching tool built on an open rule library, not "
            "a lawyer. It flags terms that routinely hurt freelancers so you know "
            "what to ask for. For anything you would bet a month of income on, "
            "pay a lawyer in your jurisdiction for an hour.", ""]
    return "\n".join(out)


def _shape_text(a: Analysis) -> str:
    s = a.shape
    bits = []
    if s.get("net_days"):
        bits.append(f"Net {s['net_days']}")
    if s.get("deposit_pct"):
        bits.append(f"{s['deposit_pct']}% deposit")
    else:
        bits.append("no deposit")
    if s.get("notice_days"):
        bits.append(f"{s['notice_days']}-day notice")
    if s.get("revision_rounds"):
        bits.append(f"{s['revision_rounds']} revision rounds")
    if s.get("term_months"):
        bits.append(f"{s['term_months']}-month term")
    if s.get("governing_law"):
        bits.append(f"law of {s['governing_law']}")
    if s.get("amounts"):
        bits.append(", ".join(s["amounts"][:3]))
    return " · ".join(bits) or "no stated numbers found"


# --------------------------------------------------------------------------- #
# Terminal
# --------------------------------------------------------------------------- #

def to_terminal(a: Analysis, narration: dict | None = None) -> str:
    n = narration or {}
    lines = [
        "",
        f"  REDPEN  ·  {a.contract.name}  ·  {a.contract.pages}p "
        f"{a.contract.clause_count} clauses",
        f"  score {a.score}/99  [{a.band.upper()}]  "
        f"{a.counts['stop']} stop / {a.counts['fix']} fix / {a.counts['ask']} ask",
        f"  {_shape_text(a)}",
        "  " + "-" * 66,
    ]
    for i, f in enumerate(a.findings, 1):
        loc = f.evidence[0].label if f.evidence else "absent"
        lines.append(f"  {i:>2}. [{SEV_ICON[f.severity]:<4}] {f.title}  ({loc})")
        if f.evidence:
            lines.append(f"      \" {f.evidence[0].quote[:96]}\"")
        lines.append(f"      fix: {f.fix[:100]}")
    em = n.get("email")
    if em:
        lines += ["  " + "-" * 66, "  NEGOTIATION EMAIL (" + em["source"] + ")", ""]
        for ln in em["body"].split("\n"):
            lines.append("    " + ln)
    lines.append("")
    return "\n".join(lines)


# --------------------------------------------------------------------------- #
# Standalone HTML brief
# --------------------------------------------------------------------------- #

def to_html(a: Analysis, narration: dict | None = None) -> str:
    n = narration or {}
    findings_html = []
    for i, f in enumerate(a.findings, 1):
        ev = "".join(
            f"<blockquote>{html.escape(e.quote)}"
            f"<cite>{html.escape(e.label)} · page {e.page} · VERBATIM</cite></blockquote>"
            for e in f.evidence[:2]
        )
        why = html.escape(n.get("explain", {}).get(f.rid, f.why))
        findings_html.append(
            f"<article class='f sev{f.severity}'>"
            f"<h3><span class='tag' style='color:{SEV_COLOR[f.severity]}'>"
            f"{SEV_ICON[f.severity]}</span> {i}. {html.escape(f.title)}</h3>"
            f"<p class='meta'>{html.escape(f.category)} · "
            f"{'term missing' if f.missing else 'expressly refused' if f.denied else 'found in'} </p>"
            f"{ev}<p>{why}</p>"
            f"<p class='fix'><b>Ask for:</b> {html.escape(f.fix)}</p>"
            f"</article>"
        )
    email = html.escape((n.get("email") or {}).get("body", ""))
    doc_data = html.escape(json.dumps(a.to_dict(), ensure_ascii=False))
    return f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>RedPen · {html.escape(a.contract.name)}</title>
<style>
 body{{margin:0;background:#0b0d12;color:#dfe4ee;font:15px/1.6 ui-monospace,Menlo,monospace}}
 main{{max-width:860px;margin:0 auto;padding:36px 22px 90px}}
 h1{{font-size:19px;letter-spacing:.16em;color:#7fe7ff;margin:0 0 4px}}
 .sub{{color:#8b93a7;font-size:13px}}
 .bar{{height:8px;background:#1b2030;border-radius:6px;margin:18px 0 6px;overflow:hidden}}
 .bar i{{display:block;height:100%;background:linear-gradient(90deg,#ffb020,#ff5d5d)}}
 .verdict{{border-left:3px solid #ff5d5d;padding:8px 14px;background:#141824;margin:16px 0 26px}}
 article{{border:1px solid #1f2536;border-radius:10px;padding:14px 16px;margin:0 0 14px;background:#101420}}
 article h3{{font-size:15px;margin:0 0 6px}}
 .tag{{letter-spacing:.1em;font-size:11px}}
 .meta{{color:#8b93a7;font-size:12px;margin:0 0 8px}}
 blockquote{{margin:6px 0;padding:8px 12px;border-left:2px solid #2b3350;background:#0c1018;font-size:13px;color:#b9c2d6}}
 blockquote cite{{display:block;color:#6f7893;font-size:11px;font-style:normal;margin-top:4px}}
 .fix{{color:#7fe7ff;font-size:13px}}
 pre{{white-space:pre-wrap;background:#0c1018;border:1px solid #1f2536;padding:14px;border-radius:10px;font-size:13px}}
 footer{{color:#6f7893;font-size:12px;margin-top:34px;border-top:1px solid #1f2536;padding-top:14px}}
</style></head><body><main>
<h1>REDPEN / OFFLINE CONTRACT REVIEW</h1>
<p class="sub">{html.escape(a.contract.name)} · {a.contract.pages} pages ·
{a.contract.clause_count} clauses · {datetime.now():%d %b %Y %H:%M} · no network used</p>
<div class="bar"><i style="width:{a.score}%"></i></div>
<p class="sub">risk score {a.score}/99 · {a.band.upper()} ·
{a.counts['stop']} stop · {a.counts['fix']} fix · {a.counts['ask']} ask</p>
<p class="sub">{html.escape(_shape_text(a))}</p>
<div class="verdict">{html.escape(BAND_COPY[a.band])}</div>
{''.join(findings_html) or '<p>No findings.</p>'}
{'<h2>Negotiation email (' + html.escape((n.get('email') or {}).get('source','')) + ')</h2><pre>' + email + '</pre>' if n.get('email') else ''}
<script type="application/json" id="redpen-data">{doc_data}</script>
<footer>RedPen is an open pattern-matching tool, not a lawyer. It flags terms that
routinely hurt freelancers. Anything you would bet a month of income on deserves an
hour of a lawyer's time in your own jurisdiction.</footer>
</main></body></html>"""
