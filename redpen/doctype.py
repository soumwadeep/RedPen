"""Document type detection and unfilled-placeholder scanning.

Both came out of running RedPen on real paperwork rather than on the synthetic
contracts in samples/.

Why type detection matters for precision: the freelance rule library asks
whether there is a deposit clause, a late-payment interest rate and a right to
suspend work. An internship offer letter has none of those, and *should not* --
so reporting them as missing findings is noise that would destroy trust in the
real findings on the same page. Rules now declare which document types they
apply to.

Why placeholder scanning matters: a draft agreement full of "[Amount]",
"[city, state]" and "___% advance" is not a bad deal, it is an unfinished one.
Telling those apart is the difference between a useful report and an alarming
one.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

SERVICES = "services"        # freelance / B2B statement of work, MSA
EMPLOYMENT = "employment"    # offer letter, internship, employment agreement
NDA = "nda"                  # confidentiality / non-disclosure agreement
UNKNOWN = "unknown"

# Signals that this is a contract at all. Without one of these there is nothing
# to review, and saying so beats scoring an onboarding checklist. Deliberately
# includes informal but obligation-bearing wording: a two-paragraph email that
# says "you will be liable for anything that goes wrong" is reviewable even
# though it never uses the word "agreement".
_CONTRACTUAL = re.compile(
    r"\b(agreement|terms and conditions|shall|whereas|part(y|ies)|"
    r"confidential information|indemnif\w*|liab\w*|obligation\w*|breach|warrant\w*|"
    r"ownership|property of|jurisdiction|governing law|termination|terminate|"
    r"notice period|intellectual property|agree[sd]?\b|payment|invoice|stipend)\b")

_MARKERS: dict[str, list[str]] = {
    NDA: [r"\bnon-?disclosure\b", r"\bnda\b", r"confidential information.{0,80}(shall|must|agrees)",
          r"obligations of (?:each )?receiving party", r"\bdisclosing party\b",
          r"keep confidential all information", r"trade secrets"],
    EMPLOYMENT: [r"\boffer letter\b", r"\bintern(ship)?\b", r"\bstipend\b", r"\bappointment\b",
                 r"\bemployee benefits\b", r"\bnotice period of\b", r"\btraining period\b",
                 r"\bfull and final\b", r"\bwe are (?:pleased|delighted|excited) to (?:offer|welcome)",
                 r"\breporting manager\b", r"\bpre-?placement offer\b", r"\bprobation\b",
                 r"\bemployee\b", r"\bemployer\b", r"\bcompany'?s (?:rules|policies)\b"],
    SERVICES: [r"\bfreelance\b", r"\bstatement of work\b", r"\bservice(s)? order\b",
               r"\bindependent contractor\b", r"\bcontractor\b", r"\bdeliverables?\b",
               r"\bschedule a\b", r"\binvoice(?:d)? (?:within|by)\b", r"\bmilestone",
               r"\bnet ?\d{1,3}\b", r"\bacceptance criteria\b", r"\bchange (?:request|order)\b"],
}

# Unfilled fields in a draft, in the shapes real templates use.
_PLACEHOLDER = re.compile(
    r"\[([^\]\n]{1,70})\]"                       # [Amount], [Effective Date]
    r"|_{3,}"                                     # ___% advance
    r"|\b(?:TBD|to be (?:decided|determined|agreed|confirmed)|not yet (?:decided|agreed))\b"
    r"|\bX{2,3},\s*XXX\b", re.I)

# Bracketed text that is a real value rather than a blank, e.g. "[5] business days"
# or "[7/15] calendar days" -- an amount chosen but left in brackets for emphasis.
_FILLED = re.compile(r"^\s*[\d.,/%]+\s*(?:business |calendar )?(?:days?|months?|years?|%)?\s*$|"
                     r"^\s*\d+(?:\s*/\s*\d+)?\s*$")


@dataclass
class DocType:
    kind: str
    confidence: float
    signals: list[str] = field(default_factory=list)
    contractual: bool = True

    @property
    def label(self) -> str:
        return {
            SERVICES: "freelance / services agreement",
            EMPLOYMENT: "offer letter or employment terms",
            NDA: "non-disclosure agreement",
            UNKNOWN: "unrecognised document",
        }[self.kind]


@dataclass
class Placeholders:
    total: int = 0
    samples: list[str] = field(default_factory=list)
    fields: list[str] = field(default_factory=list)

    @property
    def has_blanks(self) -> bool:
        return self.total > 0

    def to_dict(self) -> dict:
        return {"total": self.total, "fields": self.fields[:12], "samples": self.samples[:8]}


def classify(text: str) -> DocType:
    low = text.lower()
    if not _CONTRACTUAL.search(low):
        return DocType(UNKNOWN, 0.0, ["no contractual language found"], contractual=False)

    scores: dict[str, float] = {}
    hits: dict[str, list[str]] = {}
    for kind, pats in _MARKERS.items():
        found = [p for p in pats if re.search(p, low)]
        scores[kind] = len(found)
        hits[kind] = found

    # An NDA is often also a services agreement; the confidentiality-specific
    # signals should win when they dominate, so weight them.
    if scores[NDA] >= 2 and scores[NDA] >= scores[SERVICES]:
        best = NDA
    elif scores[EMPLOYMENT] >= 2 and scores[EMPLOYMENT] > scores[SERVICES]:
        best = EMPLOYMENT
    else:
        best = max(scores, key=lambda k: scores[k])
        if scores[best] == 0:
            best = SERVICES          # contractual but unclassifiable: assume services

    total = sum(scores.values()) or 1
    return DocType(best, round(scores[best] / total, 2),
                   [f"{k}:{len(v)}" for k, v in hits.items() if v])


def find_placeholders(text: str) -> Placeholders:
    out = Placeholders()
    seen: set[str] = set()
    for m in _PLACEHOLDER.finditer(text):
        raw = m.group(0).strip()
        inner = (m.group(1) or raw).strip()
        if _FILLED.match(inner):
            continue
        key = inner.lower()
        if key in seen:
            continue
        seen.add(key)
        out.total += 1
        if raw.startswith("["):
            out.fields.append(inner)
        else:
            out.samples.append(re.sub(r"\s+", " ", raw)[:60])
    out.samples = [s for s in out.samples if s]
    return out


def applies(rule_kind: str | None, doc_kind: str) -> bool:
    """Whether a rule runs against this document type.

    ``None`` means the rule is universal: date errors, missing liability caps and
    one-sided assignment apply to any agreement.
    """
    if not rule_kind or rule_kind == "any":
        return True
    return rule_kind == doc_kind or doc_kind == UNKNOWN
