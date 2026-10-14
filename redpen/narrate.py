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
    "clause numbers, names or facts that were not given to you: copy a company "
    "or person's name exactly as written, or leave it out. You never restate the "
    "document back to me."
)

MAX_EXPLAIN = 3          # narrate the top N findings; the rest use library text
MAX_AMBIGUITY = 3


def _src(llm: LocalLLM | None) -> str:
    """Which model actually wrote this. Never hard-coded: a swap that mislabels
    its own output would make the provenance claim in the UI false."""
    if llm is None:
        return "library"
    return (llm.model or "local").split(":")[0]


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
                    "source": _src(llm)}
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
    quote = clause.snippet(300) if clause else "(this term is absent from the document)"
    # Anchoring on the finding title matters: without it a 1B model writes about
    # whatever stands out in the clause instead of the problem we flagged.
    user = (
        f"THE PROBLEM WE FLAGGED: {f.title}\n"
        f"THE TERM ({clause.number if clause else '-'}): {quote}\n\n"
        f"In exactly two sentences, explain what can go wrong for this freelancer "
        f"because of {f.title.lower()}. Name the money or the time at risk. "
        f"Stay on that problem only. Do not repeat the clause and do not describe "
        f"any other clause."
    )
    try:
        got = sentences(llm.chat(SYSTEM, user, max_tokens=110), limit=2)
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


def _keywords(f: Finding, n: int = 3) -> list[str]:
    """Distinctive words that identify this finding's subject.

    Taken from the suggested wording rather than the headline, because a good
    paraphrase of "You lose the work the moment you make it" will not reuse the
    headline's words -- but it will talk about payment and deliverables.
    """
    stop = {"your", "you", "the", "and", "for", "with", "not", "are", "is", "to",
            "of", "on", "in", "a", "any", "all", "they", "them", "shall", "will",
            "must", "may", "each", "both", "this", "that", "under", "from", "party",
            "parties", "client", "contractor", "agreement"}
    words = [w for w in re.findall(r"[a-z]{5,}", (f.fix + " " + f.ask).lower())
             if w not in stop]
    return sorted(set(words), key=len, reverse=True)[:n]


def email_is_faithful(raw: str, items: list[tuple[Finding, str]]) -> bool:
    """Validate content, not format.

    A 1B model writes a perfectly usable email as bullets, as a numbered list,
    or as prose -- insisting on one shape would throw away good output. What
    must not happen is the email quietly dropping or inventing asks, so we check
    that most requested changes are actually represented.
    """
    if len(raw.split()) < 45:
        return False
    low = raw.lower()
    covered = 0
    for f, _loc in items:
        kws = _keywords(f)
        if kws and any(k in low for k in kws):
            covered += 1
    needed = max(1, int(len(items) * 0.6))
    return covered >= needed


_SIG = re.compile(
    r"((?:best|thanks|thank you|kind regards|regards|sincerely|cheers|many thanks"
    r"|warm regards|best wishes),?)"
    r"\s*\n+[ \t]*[-–—*_#]{0,3}[ \t]*"
    r"([A-Z][a-zA-Z .'-]{0,20}?)"
    r"[ \t]*(?:[-–—*_]{1,4})?[ \t]*$", re.I)


def sanitize_signature(body: str) -> str:
    """A 1B model will happily sign your email as "Max", or "Max --".

    Keep the closing, replace the invented name with a placeholder the user has
    to fill in -- sending an email signed with a stranger's name is the kind of
    small failure that would cost this product its credibility.
    """
    m = _SIG.search(body.rstrip())
    if m:
        if m.group(2).strip().lower() in {"yours", "yourself", "your name"}:
            return body
        return body[: m.start()] + f"{m.group(1).capitalize()},\n\n[your name]"

    # Fallback for the variant that actually shipped a "Max" into a demo: no
    # salutation at all, just a dash and a name on the last line. A lone short
    # final line after a blank is a signature, and a name there is invented.
    bare = re.search(r"\n+[ \t]*(?:[-\u2013\u2014_*]{1,4})[ \t]*"
                     r"([A-Z][a-zA-Z]{1,14})[ \t]*$", body.rstrip())
    if bare:
        return body[: bare.start()] + "\n\n[your name]"
    return body


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
        f"Max 200 words. Cover every numbered change below, in your own words, "
        f"as a list (bullets or numbers). Do not add changes that are not listed. "
        f"Sign off with '[Your name]' -- never invent a person's name.\n\n{asks}"
    )
    for attempt in range(2):
        try:
            raw = strip_preamble(llm.chat(SYSTEM, user, max_tokens=480,
                                          temperature=0.1 + 0.25 * attempt))
        except Exception:
            break
        if email_is_faithful(raw, items):
            return {"body": sanitize_signature(raw), "source": _src(llm), "count": len(items)}
    return fallback


# --------------------------------------------------------------------------- #
# 4. Ambiguity pass -- the one thing patterns genuinely cannot see
# --------------------------------------------------------------------------- #

def _resolve_clause(a: Analysis, raw_value: str) -> str | None:
    """Map the model's answer onto a clause that really exists.

    Gemma 1B often answers with the vague *word* it spotted ("reasonable",
    "promptly") instead of the clause number. Both are accepted, but a term that
    appears in several clauses is ambiguous and gets dropped rather than
    guessed at -- the user is shown a citation, so it has to be the right one.
    """
    val = str(raw_value or "").strip().lower().rstrip(".:)")
    valid = {c.number: c.number for c in a.contract.clauses}
    if val in valid:
        return valid[val]
    digits = re.search(r"\d+(?:\.\d+)*", val)
    if digits and digits.group(0) in valid:
        return digits.group(0)
    if len(val) < 4:
        return None
    holders = [c.number for c in a.contract.clauses if val in c.text.lower()]
    return holders[0] if len(holders) == 1 else None


def ambiguities(llm: LocalLLM | None, a: Analysis, limit: int = MAX_AMBIGUITY) -> list[dict]:
    """Ask the model for vague or contradictory terms the rule library is not
    looking for, then validate every citation against clauses that exist.

    Anything that cannot be resolved to one real clause is discarded. That is
    what makes it safe to show a small local model's output to a paying user.
    """
    if llm is None:
        return []
    listing = "\n".join(f"{c.number}: {c.snippet(180)}" for c in a.contract.clauses[:26])
    user = (
        "Below are clauses of a contract. Each line starts with that clause's number.\n"
        "Find up to 3 clauses that are vague, undefined or contradictory: words like "
        "'reasonable', 'promptly', 'as required', 'industry standard', an undefined "
        "scope, or two clauses that disagree.\n"
        "Answer with JSON only, exactly this shape:\n"
        "{\"items\": [{\"clause\": \"3\", \"note\": \"one short sentence\"}]}\n"
        "For clause, write only a number from the start of a line, or the single vague "
        "word you found. Never invent a number that is not shown.\n\n"
        f"{listing}"
    )
    try:
        data = parse_json(llm.chat(SYSTEM, user, max_tokens=420, json_mode=True))
        items = (data or {}).get("items") if isinstance(data, dict) else data
        out: list[dict] = []
        for it in items or []:
            if not isinstance(it, dict):
                continue
            note = str(it.get("note") or it.get("issue") or it.get("text") or "").strip()
            num = _resolve_clause(a, it.get("clause") or it.get("number") or "")
            if num and note and len(note) > 12:
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
