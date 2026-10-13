"""Rule library loading, scoping and user-authored rules.

Three catalogues, one effective set:

  catalog.py     freelance / B2B services red flags
  employment.py  offer letters, internships, employment terms
  nda.py         confidentiality agreements

Each rule declares the document type it applies to. That declaration is the
difference between a useful report and a noisy one: asked about an internship
letter, an unscoped library will happily report that you have no deposit clause
and no late-payment interest, which is true and worthless, while missing the
original marksheet sitting in the employer's drawer.

The catalogue ships in plain Python for a reason: a freelancer in a trade the
library does not know about can add their own red flag in twenty lines, or drop
a JSON file in ~/.redpen/rules/ and get it merged in at startup with no code
change and no approval from anyone. That is the practical difference between an
open rule set and a closed model's judgement -- with the latter you cannot see
the standard being applied, and you cannot change it.
"""

from __future__ import annotations

import json
import os
import re
from pathlib import Path

from .catalog import Rule, SEVERITY_LABEL, SEVERITY_LONG, negated_at, rx, expand
from .catalog import RULES as SERVICES_RULES
from .employment import EMPLOYMENT_RULES
from .nda import NDA_RULES

USER_RULES_DIR = Path(os.environ.get("REDPEN_RULES_DIR",
                                     Path.home() / ".redpen" / "rules"))

# Rules that only make sense where a freelancer is billing a client. On an
# offer letter or an NDA these produce confident nonsense.
SERVICES_ONLY = {
    "no-deposit-required", "no-late-payment-interest", "no-suspension-right",
    "no-acceptance-criteria", "no-preexisting-tools-carve-out",
    "long-payment-terms", "pay-when-paid", "satisfaction-payment",
    "set-off-rights", "all-taxes-on-you", "liquidated-damages",
    "insurance-demand", "unlimited-revisions", "unilateral-scope",
    "employee-style-control", "source-and-working-files",
    "ip-vests-on-creation", "ip-whether-or-not-paid", "portfolio-ban",
}

RULES: list[Rule] = list(SERVICES_RULES) + list(EMPLOYMENT_RULES) + list(NDA_RULES)
for _r in RULES:
    if _r.rid in SERVICES_ONLY and _r.applies_to == "any":
        _r.applies_to = "services"

ALL_RULES = RULES


def load_user_rules(directory: Path | None = None) -> list[Rule]:
    """Merge JSON rules from disk. Invalid files are reported, never fatal."""
    directory = directory or USER_RULES_DIR
    rules: list[Rule] = []
    if not directory.is_dir():
        return rules
    for path in sorted(directory.glob("*.json")):
        try:
            data = json.loads(path.read_text())
        except (json.JSONDecodeError, OSError) as exc:
            rules.append(_bad_rule(path, exc))
            continue
        for item in data if isinstance(data, list) else [data]:
            try:
                rules.append(_rule_from_dict(item))
            except (KeyError, TypeError, re.error) as exc:
                rules.append(_bad_rule(path, exc))
    return rules


def _rule_from_dict(item: dict) -> Rule:
    return Rule(
        rid=str(item["id"]),
        title=str(item.get("title", item["id"])),
        category=str(item.get("category", "terms")),
        severity=int(item.get("severity", 1)),
        why=str(item.get("why", "")),
        fix=str(item.get("fix", "")),
        ask=str(item.get("ask", "")),
        any_of=[str(p) for p in item.get("any_of", [])],
        all_of=[[str(p) for p in group] for group in item.get("all_of", [])],
        none_of=[str(p) for p in item.get("none_of", [])],
        doc_scope=bool(item.get("doc_scope", False)),
        applies_to=str(item.get("applies_to", "any")),
    )


def _bad_rule(path: Path, exc: Exception) -> Rule:
    return Rule(
        rid=f"load-error:{path.name}",
        title=f"Could not read {path.name}",
        category="terms", severity=0,
        why=f"{type(exc).__name__}: {exc}", fix="", ask="",
    )


def all_rules(extra: list[Rule] | None = None) -> list[Rule]:
    """Full effective rule set: built-in plus user rules, deduplicated by id."""
    rules = list(RULES)
    seen = {r.rid for r in rules}
    for r in (extra if extra is not None else load_user_rules()):
        if r.rid not in seen:
            rules.append(r)
            seen.add(r.rid)
    return rules


def counts() -> dict:
    from collections import Counter

    return {
        "total": len(RULES),
        "by_scope": dict(Counter(r.applies_to for r in RULES)),
        "by_severity": dict(Counter(r.severity for r in RULES)),
        "doc_wide": sum(1 for r in RULES if r.doc_scope),
    }


__all__ = ["Rule", "RULES", "ALL_RULES", "SERVICES_RULES", "EMPLOYMENT_RULES",
           "NDA_RULES", "SERVICES_ONLY", "SEVERITY_LABEL", "SEVERITY_LONG",
           "negated_at", "rx", "expand", "load_user_rules", "all_rules",
           "counts", "USER_RULES_DIR"]
