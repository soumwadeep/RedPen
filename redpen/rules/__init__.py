"""Rule library loading, including user-authored rules.

The catalogue ships in plain Python for a reason: a freelancer in a trade the
library does not know about can add their own red flag in twenty lines, or drop
a JSON file in ~/.redpen/rules/ and get it merged in at startup with no code
change and no re-approval from anyone. That is the practical difference between
an open rule set and a closed model's judgement -- with the latter you cannot
see the standard being applied, and you cannot change it.
"""

from __future__ import annotations

import json
import os
import re
from pathlib import Path

from .catalog import CLAUSE_RULES, RULES, SEVERITY_LABEL, ABSENCE_RULES, Rule

USER_RULES_DIR = Path(os.environ.get("REDPEN_RULES_DIR",
                                     Path.home() / ".redpen" / "rules"))


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


__all__ = ["Rule", "RULES", "CLAUSE_RULES", "ABSENCE_RULES", "SEVERITY_LABEL",
           "load_user_rules", "all_rules", "USER_RULES_DIR"]
