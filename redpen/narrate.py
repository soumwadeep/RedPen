"""What the language model is for -- and what it is never allowed to do.

The deterministic engine decides which clauses are dangerous. Gemma only reads
what the engine already found and turns it into language a freelancer can send:
a briefing, a plain-English explanation in the context of *this* contract, a
negotiation email, and a pass at ambiguity the patterns cannot see.

Every function here has a written fallback, so if the 1B model returns junk the
report is still complete. That is a deliberate design consequence of running a
small local model instead of a huge hosted one.
"""

from __future__ import annotations

import re

from .engine import Analysis, Finding
from .ingest import Contract
from .llm import LocalLLM, bullets, labelled, parse_json, sentences, strip_preamble

SYSTEM = (
    "You help freelancers understand contracts. You are not a lawyer and never "
    "claim to be. You write short, plain, specific sentences. You never invent "
    "clause numbers or facts that were not given to you. You never restate the "
    "document back to me."
)

MAX_EXPLAIN = 3          # narrate the top N findings; the rest use library text
MAX_AMBIGUITY = 3


# --------------------------------------------------------------------------- #
# Shared context packing
# --------------------------------------------------------------------------- #

def _shape_line(a: Analysis) -> str:
    s = a.shape
    bits = []
    if s.get("net_days"):
        bits.append(f"payment {s['net_days']} days after invoice")
    if s.get("deposit_pct"):
        bits.append(f"{s['deposit_pct']}% deposit")
    else:
        bits.append("no deposit")
    if s.get("notice_days"):
        bits.append(f"{s['notice_days']} days notice")
    if s.get("revision_rounds"):
        bits.append(f"revisions: {s['revision_rounds']}")
    if s.get("term_months"):
        bits.append(f"{s['term_months']} month term")
    if s.get("governing_law"):
        bits.append(f"law of {s['governing_law']}")
    if s.get("amounts"):
        bits.append("figures: " + ", ".join(s["amounts"][:3]))
    return "; ".join(bits) or "no stated numbers found"


def _headings(a: Analysis, limit: int = 14) -> str:
    return " | ".join(f"{c.number} {c.heading}".strip() for c in a.contract.clauses[:limit]) or "(no headings)"


def _finding_titles(a: Analysis, limit: int = 8) -> str:
    return "\n".join(f"- {f.title}" for f in a.findings[:limit]) or "- none"


# --------------------------------------------------------------------------- #
# 1. Briefing
# --------------------------------------------------------------------------- #

def overview(llm: LocalLLM | None, a: Analysis) -> dict:
    fallback = {
        "deal": _shape_line(a),
        "worst": (a.findings[0].title if a.findings else "Nothing in the library matched."),
        "first": (a.findings[0].ask if a.findings else "No changes needed."),
        "source": "library",
    }
    if llm is None:
        return fallback
    user = (
        f"CONTRACT: {a.contract.name} ({a.contract.pages} pages, "
        f"{a.contract.clause_count} clauses)\n"
        f"STATED TERMS: {_shape_line(a)}\n"
        f"CLAUSES: {_headings(a)}\n"
        f"PROBLEMS FOUND BY THE RULES:\n{_finding_titles(a)}\n\n"
        "Answer with exactly these three lines, nothing else:\n"
        "DEAL: one sentence on what this agreement is\n"
        "WORST: one sentence naming the single most damaging problem\n"
        "FIRST: one sentence on the first thing to ask them to change"
    )
    try:
        raw = llm.chat(SYSTEM, user, max_tokens=200)
        got = labelled(raw, ["DEAL", "WORST", "FIRST"])
        if got.get("worst"):
            return {"deal": got.get("deal") or fallback["deal"],
                    "worst": got["worst"],
                    "first": got.get("first") or fallback["first"],
                    "source": "gemma"}
    except Exception:
        pass
    return fallback


# --------------------------------------------------------------------------- #
# 2. Per-finding explanation in context
# --------------------------------------------------------------------------- #

def explain(llm: LocalLLM | None, a: Analysis, f: Finding) -> str:
    clause = a.contract.clause(f.evidence[0].cid) if f.evidence else None
    if llm is None:
        return f.why
    quote = clause.snippet(300) if clause else "(term absent from the document)"
    user = (
        f"CLAUSE {clause.number if clause else '-'} says:\n{quote}\n\n"
        f"A rule flagged this because: {f.why}\n\n"
        "In two sentences, tell this freelancer what can actually go wrong for "
        "them in this deal. Name the money or the time at risk. Do not repeat "
        "the clause."
    )
    try:
        got = sentences(llm.chat(SYSTEM, user, max_tokens=120), limit=2)
        if got and len(" ".join(got)) > 40:
            return " ".join(got)
    except Exception:
        pass
    return f.why


# --------------------------------------------------------------------------- #
# 3. The negotiation email
# --------------------------------------------------------------------------- #

def _ask_list(a: Analysis, limit: int = 6) -> list[tuple[Finding, str]]:
    seen: set[str] = set()
    out: list[tuple[Finding, str]] = []
    for f in a.findings:
        if f.rid in seen or f.severity == 0:
            continue
        seen.add(f.rid)
        loc = ""
        if f.evidence:
            loc = ", ".join(f"{e.label} (p.{e.page})" for e in f.evidence[:2])
        elif f.missing:
            loc = "not in the agreement"
        out.append((f, loc))
        if len(out) >= limit:
            break
    return out


def email_fallback(a: Analysis, fee: str = "the quoted fee") -> str:
    """Deterministic email -- always available, no model needed."""
    items = _ask_list(a)
    lines = [
        f"Re: {a.contract.name} - a few changes before I sign",
        "",
        "Thanks for sending this over. I want to get started, and there are a "
        "handful of clauses I need to adjust so the risk sits sensibly for both "
        "of us. I've put my suggested wording next to each one.",
        "",
    ]
    for i, (f, loc) in enumerate(items, 1):
        lines.append(f"{i}. {f.title} [{loc}]")
        lines.append(f"   Suggested: {f.fix}")
        lines.append("")
    lines += [
        f"Nothing here is a dealbreaker - {fee} and the timeline still work if "
        "we can land these. Happy to jump on a call and walk through them.",
        "",
        "Thanks,",
    ]
    return "\n".join(lines)


def negotiation_email(llm: LocalLLM | None, a: Analysis, tone: str = "warm") -> dict:
    fallback = {"body": email_fallback(a), "source": "template", "count": len(_ask_list(a))}
    if llm is None:
        return fallback
    items = _ask_list(a)
    if not items:
        return {"body": "No changes to request - the review found nothing worth "
                        "raising before signing.", "source": "template", "count": 0}
    asks = "\n".join(
        f"{i}. {f.title} (clause {loc}): ask for \"{f.ask}\" | wording: {f.fix}"
        for i, (f, loc) in enumerate(items, 1)
    )
    tone_line = {
        "warm": "Friendly and grateful. We are early in the relationship.",
        "direct": "Brief and firm. Bullet the changes, no apology.",
        "formal": "Neutral business tone, full sentences, no contractions.",
    }.get(tone, "Friendly and professional.")
    user = (
        f"Write an email from a freelancer to their client asking for these "
        f"contract changes. {tone_line}\n"
        f"Max 200 words. Number the changes and keep each to one or two "
        f"sentences. Do not invent changes that are not in this list.\n\n{asks}"
    )
    try:
        raw = strip_preamble(llm.chat(SYSTEM, user, max_tokens=520))
        if len(raw.split()) > 40 and re.search(r"1[.)]", raw):
            return {"body": raw, "source": "gemma", "count": len(items)}
    except Exception:
        pass
    return fallback


# --------------------------------------------------------------------------- #
# 4. Ambiguity pass -- the one thing patterns genuinely cannot see
# --------------------------------------------------------------------------- #

def ambiguities(llm: LocalLLM | None, a: Analysis, limit: int = MAX_AMBIGUITY) -> list[dict]:
    """Ask the model for vague or contradictory terms the rule library is not
    looking for, then validate every citation against clauses that exist.

    Anything pointing at a clause number that is not in the document is
    discarded. That is what makes it safe to show a small model's output to a
    paying user.
    """
    if llm is None:
        return []
    valid = {c.number for c in a.contract.clauses}
    listing = "\n".join(f"{c.number}: {c.snippet(180)}" for c in a.contract.clauses[:26])
    user = (
        "Below are clauses from a contract, each prefixed by its number.\n"
        "List up to 3 clauses that are vague, contradictory, or missing a "
        "definition a freelancer would need -- things like 'reasonable', "
        "'as required', 'promptly', 'industry standard', undefined scope, or "
        "two clauses that conflict.\n"
        "Reply with JSON only: {\"items\": [{\"clause\": \"<number>\", "
        "\"note\": \"<one short sentence>\"}]}\n"
        "Use only numbers that appear below.\n\n"
        f"{listing}"
    )
    try:
        data = parse_json(llm.chat(SYSTEM, user, max_tokens=400, json_mode=True))
        items = (data or {}).get("items") if isinstance(data, dict) else data
        out: list[dict] = []
        for it in items or []:
            if not isinstance(it, dict):
                continue
            num = str(it.get("clause", "")).strip().rstrip(".:")
            note = str(it.get("note", "")).strip()
            if num in valid and note:
                out.append({"clause": num, "note": note})
            if len(out) >= limit:
                break
        return out
    except Exception:
        return []


# --------------------------------------------------------------------------- #
# Orchestration
# --------------------------------------------------------------------------- #

def narrate(llm: LocalLLM | None, a: Analysis, want: set[str] | None = None) -> dict:
    """Produce the model layer for one review. `want` picks the expensive bits."""
    want = want or {"overview", "email", "explain", "ambiguity"}
    out: dict = {}
    if "overview" in want:
        out["overview"] = overview(llm, a)
    if "email" in want:
        out["email"] = negotiation_email(llm, a)
    if "explain" in want:
        notes = {}
        for f in a.findings[:MAX_EXPLAIN]:
            notes[f.rid] = explain(llm, a, f)
        out["explain"] = notes
    if "ambiguity" in want:
        out["ambiguity"] = ambiguities(llm, a)
    return out
