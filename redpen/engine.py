"""Deterministic analysis: run the rule library over a contract.

No model runs in this file. Everything here is reproducible from the document
alone, which is what lets a user trust the report and let us use the model only
for language. Produces findings with the exact matched words as evidence, plus
a 'deal shape' summary pulled out of the numbers the contract actually states.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

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

    def to_dict(self, include_text: bool = True) -> dict:
        return {
            "document": {
                "name": self.contract.name,
                "source": self.contract.source,
                "pages": self.contract.pages,
                "clauses": self.contract.clause_count,
                "words": len(self.contract.text.split()),
                "warnings": self.contract.warnings,
            },
            "score": self.score,
            "band": self.band,
            "counts": self.counts,
            "shape": self.shape,
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
    # not the deal value, and showing it erodes trust in the whole panel.
    for m in re.finditer(
            r"([^.;]{0,70}?(?:fee|total|fixed|deposit|rate|price|invoice|charge)[^.;]{0,70}?)",
            flow):
        window = m.group(1)
        for mm in _MONEY.finditer(window):
            v = mm.group(0).strip()
            if re.search(r"expense|over\s$|\bunder\b|threshold", window, re.I):
                continue
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
    rules = all_rules(extra_rules)
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
                    band=_band(score), shape=deal_shape(contract), counts=counts)
