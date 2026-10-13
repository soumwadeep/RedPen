"""Deterministic analysis: run the rule library over a contract.

No model runs in this file. Everything here is reproducible from the document
alone, which is what lets a user trust the report and let us use the model only
for language. Produces findings with the exact matched words as evidence, plus
a 'deal shape' summary pulled out of the numbers the contract actually states.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from . import doctype
from .ingest import Contract, normalise
from .rules import all_rules
from .rules.catalog import SEVERITY_LABEL, negated_at, rx

# --------------------------------------------------------------------------- #
# Absence rules: missing vs expressly refused
# --------------------------------------------------------------------------- #

_ANCHOR_WORDS = {
    "money": r"payment|invoice|fee|price|deposit",
    "ip": r"property|deliverable|assign|intellectual",
    "risk": r"liab|indemn|insurance|damage|claim",
    "exit": r"terminat|renew|notice|assign|expir",
    "terms": r"confidential|governing|dispute|entire|survive",
    "control": r"scope|revision|work|services|availab",
}


def _absence_state(rule, doc_flow: str) -> tuple[str, int, int]:
    """Return ('ok'|'absent'|'denied', start, end) for a whole-document rule.

    Shares one negation rule with the clause rules: a protective term that is
    mentioned only to be refused is a refusal, not a safeguard. Context groups
    must also be present, so a stray word is not credited as a term.
    """
    context_ok = all(any(rx(p).search(doc_flow) for p in group) for group in rule.all_of)
    first_negated = None
    for pat in rule.any_of:
        for m in rx(pat).finditer(doc_flow):
            if not negated_at(doc_flow, m.start()) and context_ok:
                return "ok", m.start(), m.end()
            if first_negated is None:
                first_negated = m
    if first_negated is not None:
        return "denied", first_negated.start(), first_negated.end()
    return "absent", 0, 0


def _anchor(contract: Contract, flows: dict[str, str], rule) -> list[Evidence]:
    """Point an absence finding at the clause the term would belong in, so the
    reader lands in the right place instead of clause 1."""
    probe = re.compile(_ANCHOR_WORDS.get(rule.category, r"payment|liab|terminat|scope"))
    scored: list[tuple[int, Evidence]] = []
    for clause in contract.clauses:
        flow = flows[clause.cid]
        hits = list(probe.finditer(flow))
        if not hits:
            continue
        h = hits[0]
        scored.append((len(hits), Evidence(clause.cid, clause.label, clause.page,
                                           _quote(flow, h.start(0), h.end(0)))))
    if not scored:
        return []
    scored.sort(key=lambda t: -t[0])
    return [scored[0][1]]


WEIGHT = {3: 16, 2: 7, 1: 3, 0: 0}

_MONEY = re.compile(r"(?:usd|\$|€|£|inr|₹|eur|gbp)\s?[\d,]{2,9}(?:\.\d{1,2})?|[\d,]{2,9}(?:\.\d{1,2})?\s?(?:usd|eur|gbp|inr)")
_NUM_DAYS = re.compile(r"(\d{1,3})\s*(?:business |calendar )?days?")


@dataclass
class Evidence:
    cid: str
    label: str
    page: int
    quote: str

    def to_dict(self) -> dict:
        return {"cid": self.cid, "label": self.label, "page": self.page, "quote": self.quote}


@dataclass
class Finding:
    rid: str
    title: str
    category: str
    severity: int
    why: str
    fix: str
    ask: str
    evidence: list[Evidence] = field(default_factory=list)
    missing: bool = False      # True = the protective term is absent
    denied: bool = False       # True = the term is present but expressly refused
    placeholder: bool = False  # True = the trigger text is an unfilled blank

    @property
    def band(self) -> str:
        return SEVERITY_LABEL[self.severity]

    @property
    def weight(self) -> int:
        return WEIGHT[self.severity]

    @property
    def pages(self) -> list[int]:
        return sorted({e.page for e in self.evidence})

    @property
    def presence(self) -> str:
        if self.denied:
            return "refused"
        if self.missing:
            return "missing"
        return "present"

    def to_dict(self) -> dict:
        return {
            "rid": self.rid,
            "title": self.title,
            "category": self.category,
            "severity": self.severity,
            "band": self.band,
            "why": self.why,
            "fix": self.fix,
            "ask": self.ask,
            "missing": self.missing,
            "denied": self.denied,
            "placeholder": self.placeholder,
            "presence": self.presence,
            "pages": self.pages,
            "evidence": [e.to_dict() for e in self.evidence],
        }


@dataclass
class Analysis:
    contract: Contract
    findings: list[Finding]
    score: int
    band: str
    shape: dict
    counts: dict
    doc_type: doctype.DocType = field(default_factory=lambda: doctype.DocType("unknown", 0.0))
    blanks: doctype.Placeholders = field(default_factory=doctype.Placeholders)

    def to_dict(self, include_text: bool = True) -> dict:
        return {
            "document": {
                "name": self.contract.name,
                "source": self.contract.source,
                "pages": self.contract.pages,
                "clauses": self.contract.clause_count,
                "words": len(self.contract.text.split()),
                "warnings": self.contract.warnings,
                "type": self.doc_type.kind,
                "type_label": self.doc_type.label,
                "type_confidence": self.doc_type.confidence,
                "contractual": self.doc_type.contractual,
            },
            "score": self.score,
            "band": self.band,
            "counts": self.counts,
            "shape": self.shape,
            "blanks": self.blanks.to_dict(),
            "findings": [f.to_dict() for f in self.findings],
            "clauses": [c.to_dict() for c in self.contract.clauses] if include_text else [],
        }


# --------------------------------------------------------------------------- #
# Evidence
# --------------------------------------------------------------------------- #

def _quote(flow: str, start: int, end: int, pad: int = 70) -> str:
    lo = max(start - pad, 0)
    hi = min(end + pad, len(flow))
    text = flow[lo:hi].strip()
    if lo > 0:
        text = "…" + text
    if hi < len(flow):
        text = text + " …"
    return text


def _span_for_evidence(rule, flow: str) -> tuple[int, int] | None:
    """The asserted offending text, chosen for how readable it is as a quote."""
    spans = rule.hits(flow)
    if not spans:
        for group in rule.all_of:
            for pat in group:
                m = rx(pat).search(flow)
                if m:
                    return m.start(0), m.end(0)
        return None
    # Longest span usually carries the clause's own words rather than one verb.
    return max(spans, key=lambda s: s[1] - s[0])


# --------------------------------------------------------------------------- #
# Deal shape -- numbers the contract actually states
# --------------------------------------------------------------------------- #

def deal_shape(contract: Contract) -> dict:
    flow = re.sub(r"\s+", " ", normalise(contract.text))
    from .rules.catalog import max_net_days, longest_notice

    shape: dict = {
        "net_days": max_net_days(flow) or None,
        "notice_days": longest_notice(flow) or None,
        "amounts": [],
        "revision_rounds": None,
        "term_months": None,
        "governing_law": None,
        "late_interest": None,
        "deposit_pct": None,
    }

    seen: set[str] = set()
    # Only report figures that sit in a fee context: "expenses over 50 USD" is
    # not the deal value, and showing it erodes trust in the whole panel. The
    # trailing window must stay greedy -- a lazy one matches empty, so the
    # amount never lands inside it and FIGURES renders blank.
    for m in re.finditer(
            r"[^.;]{0,70}?(?:fee|total|fixed|deposit|rate|price|invoice|charge)[^.;]{0,70}",
            flow):
        window = m.group(0)
        if re.search(r"expense|threshold|\bunder\b", window, re.I):
            continue
        for mm in _MONEY.finditer(window):
            v = mm.group(0).strip()
            if v not in seen:
                seen.add(v)
                shape["amounts"].append(v)
        if len(shape["amounts"]) >= 4:
            break

    rev = re.search(r"(\d{1,2})\s*(?:rounds?|iterations?)[^.]{0,34}revisions?", flow)
    if rev:
        shape["revision_rounds"] = int(rev.group(1))
    elif re.search(r"unlimited revisions", flow):
        shape["revision_rounds"] = "unlimited"

    term = re.search(r"(?:term of|for a period of|initial term)\D{0,12}(\d{1,2})\s*(?:calen|calendar |business )?months?", flow)
    if term:
        shape["term_months"] = int(term.group(1))

    law = re.search(r"laws? of (?:the )?([a-z ]{3,32}?)(?:,|\.|;)", flow)
    if law:
        shape["governing_law"] = law.group(1).strip().title()

    li = re.search(r"interest (?:of |at )?([\d.]{1,4})\s*%[^.;]{0,40}(?:month|year|annum)", flow)
    if li:
        shape["late_interest"] = f"{li.group(1)}%/{'month' if 'month' in li.group(0) else 'year'}"

    dep = re.search(r"(\d{1,3})\s*%[^.;]{0,40}(?:deposit|in advance|upfront|on signature|on commencement)", flow)
    if dep:
        shape["deposit_pct"] = int(dep.group(1))

    return shape


def _band(score: int) -> str:
    if score >= 45:
        return "high"
    if score >= 22:
        return "medium"
    if score >= 8:
        return "low"
    return "clean"


# --------------------------------------------------------------------------- #
# Run
# --------------------------------------------------------------------------- #

def analyse(contract: Contract, extra_rules: list | None = None) -> Analysis:
    kind = doctype.classify(contract.text)
    blanks = doctype.find_placeholders(contract.text)

    if not kind.contractual:
        # An onboarding checklist or a job description is not an agreement.
        # Scoring one would manufacture findings out of prose that makes no
        # promises, so the honest output is "nothing to review".
        return Analysis(contract=contract, findings=[], score=0, band="clean",
                        shape=deal_shape(contract),
                        counts={"stop": 0, "fix": 0, "ask": 0, "total": 0},
                        doc_type=kind, blanks=blanks)

    rules = [r for r in all_rules(extra_rules)
             if doctype.applies(r.applies_to, kind.kind)]
    clause_rules = [r for r in rules if not r.doc_scope]
    absence_rules = [r for r in rules if r.doc_scope]

    doc_flow = re.sub(r"\s+", " ", normalise(contract.text))
    flows = {
        c.cid: re.sub(r"\s+", " ", normalise(c.text))
        for c in contract.clauses
    }
    findings: list[Finding] = []

    for rule in clause_rules:
        evidence: list[Evidence] = []
        for clause in contract.clauses:
            flow = flows[clause.cid]
            if not rule.matches(flow):
                continue
            if rule.where is not None and not rule.where(flow):
                continue
            span = _span_for_evidence(rule, flow)
            quote = _quote(flow, *span) if span else clause.snippet(220)
            evidence.append(Evidence(clause.cid, clause.label, clause.page, quote))
        if evidence:
            findings.append(Finding(
                rid=rule.rid, title=rule.title, category=rule.category,
                severity=rule.severity, why=rule.why, fix=rule.fix, ask=rule.ask,
                evidence=evidence,
            ))

    # Absence rules: the finding is that a protective term appears nowhere in
    # the document -- or appears only to be expressly refused, which is worse.
    for rule in absence_rules:
        state, start, end = _absence_state(rule, doc_flow)
        if state == "ok":
            continue
        evidence: list[Evidence] = []
        needle = doc_flow[start:end].strip()
        if needle:
            for clause in contract.clauses:
                flow = flows[clause.cid]
                at = flow.find(needle)
                if at >= 0:
                    evidence = [Evidence(clause.cid, clause.label, clause.page,
                                         _quote(flow, at, at + len(needle)))]
                    break
        if not evidence:
            evidence = _anchor(contract, flows, rule)
        findings.append(Finding(
            rid=rule.rid, title=rule.title, category=rule.category,
            severity=rule.severity, why=rule.why, fix=rule.fix, ask=rule.ask,
            evidence=evidence,
            missing=(state == "absent"),
            denied=(state == "denied"),
        ))

    findings.extend(date_checks(contract, flows))

    # A finding whose trigger text is still a blank is advice to fill the form,
    # not evidence of a hostile term. "[city, state] will have exclusive
    # jurisdiction" is an unfinished draft; "Wilmington, Delaware" is a decision
    # made against you. Reporting them identically is how a report stops being
    # trustworthy, so blanks are tagged and demoted one level.
    blank = re.compile(r"\[[^\]]{1,70}\]|_{3,}|\b(?:tbd|to be (?:decided|determined|agreed))\b", re.I)
    for f in findings:
        if any(blank.search(e.quote) for e in f.evidence):
            f.placeholder = True
            f.severity = max(1, f.severity - 1)

    findings.sort(key=lambda f: (-f.severity, -len(f.evidence), f.category))
    raw = sum(f.weight for f in findings)
    # Saturating scale: one serious finding lands around 30, a genuinely hostile
    # document approaches 100 without pretending to be certain of it. It is an
    # ordering signal for triage, not a probability of anything.
    score = min(99, round(100 * (1 - 2.718281828 ** (-raw / 45)))) if raw else 0
    counts = {
        "stop": sum(1 for f in findings if f.severity == 3),
        "fix": sum(1 for f in findings if f.severity == 2),
        "ask": sum(1 for f in findings if f.severity == 1),
        "total": len(findings),
    }
    return Analysis(contract=contract, findings=findings, score=score,
                    band=_band(score), shape=deal_shape(contract), counts=counts,
                    doc_type=kind, blanks=blanks)


_MON = {m: i for i, m in enumerate(
    ["jan", "feb", "mar", "apr", "may", "jun",
     "jul", "aug", "sep", "oct", "nov", "dec"], start=1)}

_DATE = re.compile(
    r"(?:(\d{1,2})\s*[-/]\s*(\d{1,2})\s*[-/]\s*(\d{2,4}))"          # 29/06/2023
    r"|(?:(\d{1,2})(?:st|nd|rd|th)?[\s/-]+([a-z]{3,9})\.?[\s/-]+(\d{4}))"  # 3-Jul-2022
    r"|(?:([a-z]{3,9})\.?[\s/-]+(\d{1,2})(?:st|nd|rd|th)?[,\s/-]+(\d{4}))",  # Jul 3 2022
    re.I)

# "Date:" is also the tail of "Start Date:" and "End Date:", so a letter date
# must not be preceded by one of those labels.
_LETTER_DATE = re.compile(
    r"(?<!start )(?<!end )(?<!joining )(?<!birth )(?<!issued )\bdate\s*[:\-]\s*"
    r"(\d{1,2}\s*[-/]\s*\d{1,2}\s*[-/]\s*\d{2,4}"
    r"|\d{1,2}(?:st|nd|rd|th)?\s+[a-z]{3,9}\.?\s+\d{4}"
    r"|[a-z]{3,9}\.?\s+\d{1,2}(?:st|nd|rd|th)?,?\s+\d{4})", re.I)


def _parse_date(text: str) -> tuple[int, int, int] | None:
    m = _DATE.search(text)
    if not m:
        return None
    g = m.groups()
    try:
        if g[0]:
            d, mo, y = int(g[0]), int(g[1]), int(g[2])
        elif g[3]:
            d, mo, y = int(g[3]), _MON[g[4][:3].lower()], int(g[5])
        else:
            d, mo, y = int(g[7]), _MON[g[6][:3].lower()], int(g[8])
    except (KeyError, TypeError, ValueError):
        return None
    if y < 100:
        y += 2000
    if not (1 <= mo <= 12 and 1 <= d <= 31):
        return None
    return y, mo, d


def _label(contract: Contract, flows: dict, needle: str) -> Evidence | None:
    for clause in contract.clauses:
        at = flows[clause.cid].find(needle)
        if at >= 0:
            return Evidence(clause.cid, clause.label, clause.page,
                            _quote(flows[clause.cid], at, at + len(needle)))
    return None


def date_checks(contract: Contract, flows: dict[str, str]) -> list[Finding]:
    """Dates that cannot be true, which no keyword rule can catch.

    Found by accident on a real internship letter dated 29/06/2023 whose
    internship started 3-Jul-2022 and ended 28-Apr-2023 -- a term that had
    already finished before the offer was written.
    """
    flow = re.sub(r"\s+", " ", normalise(contract.text))
    out: list[Finding] = []

    def grab(pattern: str | re.Pattern) -> tuple[str, tuple[int, int, int]] | None:
        m = pattern.search(flow) if isinstance(pattern, re.Pattern) else re.search(pattern, flow, re.I)
        if not m:
            return None
        d = _parse_date(m.group(0))
        return (m.group(0), d) if d else None

    # Both date shapes belong inside the label's group. Written as a top-level
    # alternation, the bare form matches the letter's own date first, and every
    # check then compares that date against itself.
    _D = (r"(?:\d{1,2}\s*[-/]\s*(?:\d{1,2}|[a-z]{3,9})\s*[-/]\s*\d{2,4}"
          r"|\d{1,2}(?:st|nd|rd|th)?\s+[a-z]{3,9}\.?\s+\d{4}"
          r"|[a-z]{3,9}\.?\s+\d{1,2}(?:st|nd|rd|th)?,?\s+\d{4})")
    letter = grab(_LETTER_DATE)
    start = grab(r"(?:start date|commencing on|to begin on|begin on|date of joining"
                 r"|joining on|scheduled to begin on)\s*[:\-]?\s*" + _D)
    end = grab(r"(?:end date|ending on|will end on|conclude on|end(?:ing)? date"
               r"|scheduled to end on)\s*[:\-]?\s*" + _D)

    ld = _parse_date(letter[0]) if letter else None
    sd = _parse_date(start[0]) if start else None
    ed = _parse_date(end[0]) if end else None

    if sd and ed and ed < sd:
        out.append(Finding(
            rid="dates-impossible-order",
            title="The end date falls before the start date",
            category="terms", severity=3,
            why=("As written, the engagement finishes before it begins. That is not "
                 "a typo to smile at: whichever date is wrong, one side's "
                 "commitment is undefined, and disputes about tenure, notice and "
                 "when pay starts are decided by whoever wrote the document."),
            fix=("The engagement begins on [start date] and ends on [end date], "
                 "both stated in the same format and after the date of this letter."),
            ask=("The dates don't line up -- the end is before the start. Can you "
                 "confirm the correct term?"),
            evidence=[e for e in (_label(contract, flows, n[0]) for n in (start, end) if n) if e]))
    if ld and sd and sd < ld:
        out.append(Finding(
            rid="dates-start-before-letter",
            title="The start date is before the letter itself",
            category="terms", severity=3,
            why=("You are being offered a role that, on these dates, has already "
                 "started or finished. Either the template was reused without "
                 "updating or the term is not what it says -- and both mean the "
                 "written dates cannot be relied on."),
            fix="The commencement date is [date], which is on or after the date of this letter.",
            ask="The joining date in here is earlier than the letter date -- can you "
                 "reissue with the correct dates?",
            evidence=[e for e in (_label(contract, flows, n[0]) for n in (letter, start) if n) if e]))
    return [f for f in out if f.rid]
