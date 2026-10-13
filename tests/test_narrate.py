"""The guard-rails between a 1B model's output and a paying user's inbox.

None of these need an engine: they test the validation and repair logic that
decides whether model output is shown at all.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from redpen import narrate
from redpen.engine import Finding
from redpen.ingest import load, load_text
from redpen.engine import analyse
from redpen.llm import bullets, labelled, parse_json, sentences, strip_preamble

SAMPLES = Path(__file__).resolve().parent.parent / "samples"


# --------------------------------------------------------------------------- #
# Signature repair
# --------------------------------------------------------------------------- #

@pytest.mark.parametrize("tail", [
    "Sincerely,\n\nMax",
    "Sincerely,\n\nMax --",
    "Best,\n\nMax",
    "best regards,\n\n*Max*",
    "Thanks\n\n— Max",
    "Kind regards,\n\nMax\n",
])
def test_invented_signoff_names_are_replaced(tail):
    body = "Hi there,\n\nCould we move the IP transfer?\n\n" + tail
    out = narrate.sanitize_signature(body)
    assert "[your name]" in out
    assert "Max" not in out


def test_a_real_placeholder_is_left_alone():
    body = "Hi,\n\ncan we change clause 4?\n\nBest,\n\n[your name]"
    assert "[your name]" in narrate.sanitize_signature(body)
    assert narrate.sanitize_signature(body).count("[your name]") == 1


def test_email_body_without_a_signoff_is_untouched():
    body = "Hi,\n\nTwo changes please:\n1. IP on payment\n2. Net 15"
    assert narrate.sanitize_signature(body) == body


# --------------------------------------------------------------------------- #
# Faithfulness gate
# --------------------------------------------------------------------------- #

def _items(path: str, n: int = 3):
    """Real findings, because the coverage check reads the wording a user is
    being asked to request -- synthetic fix text would test nothing."""
    a = analyse(load(SAMPLES / path))
    return [(f, f.evidence[0].label if f.evidence else "-")
            for f in a.findings[:n]]


ITEMS = _items("lumen_typical.txt")


def test_faithfulness_accepts_bullets_and_prose_not_just_numbers():
    assert len(ITEMS) == 3
    bullets_mail = (
        "Hi, a few changes before I sign:\n"
        "* title to each deliverable should pass on payment in full\n"
        "* the fee covers two rounds of consolidated revisions, further rounds billed hourly\n"
        "* I need to be able to show the work in my portfolio after launch\n"
        "Thanks, looking forward to it.")
    assert narrate.email_is_faithful(bullets_mail, ITEMS)


def test_faithfulness_rejects_an_email_that_drops_the_asks():
    assert not narrate.email_is_faithful(
        "Hi, looking forward to starting the project! Let me know if you need "
        "anything at all from me before we kick off. I am excited about the "
        "timeline and think it will be a great collaboration for both of us.", ITEMS)


def test_faithfulness_rejects_a_stub():
    assert not narrate.email_is_faithful("Sure, here you go.", ITEMS)


# --------------------------------------------------------------------------- #
# Citation validation -- the anti-hallucination guard
# --------------------------------------------------------------------------- #

def test_clause_resolution_accepts_numbers_and_ranges():
    a = analyse(load(SAMPLES / "lumen_typical.txt"))
    assert narrate._resolve_clause(a, "3") == "3"
    assert narrate._resolve_clause(a, "Clause 3") == "3"
    assert narrate._resolve_clause(a, "3.") == "3"


def test_clause_resolution_maps_a_vague_word_to_its_only_clause():
    a = analyse(load(SAMPLES / "lumen_typical.txt"))
    assert narrate._resolve_clause(a, "satisfied") == "1"


def test_clause_resolution_rejects_invented_numbers():
    a = analyse(load(SAMPLES / "lumen_typical.txt"))
    assert narrate._resolve_clause(a, "47") is None
    assert narrate._resolve_clause(a, "Schedule Z") is None
    assert narrate._resolve_clause(a, "") is None


def test_ambiguous_word_across_clauses_is_dropped_not_guessed():
    text = (
        "1. PAYMENT. Client shall pay within a reasonable period after invoice, "
        "and reasonable expenses will be considered from time to time.\n\n"
        "2. SCOPE. Designer shall provide reasonable access to files, and any "
        "reasonable request made by the client will be accommodated promptly.\n\n"
        "3. TERM. Either party may end this on 30 days written notice and pay for "
        "work done. Fees are fixed and payable in the currency stated.\n"
    )
    a = analyse(load_text("two-reasonable", text))
    assert narrate._resolve_clause(a, "reasonable") is None


# --------------------------------------------------------------------------- #
# Small-model output hygiene
# --------------------------------------------------------------------------- #

def test_preamble_is_stripped():
    assert strip_preamble("Here's a three-line explanation of that clause:\nRISK: bad").startswith("RISK")
    assert strip_preamble("Sure! Here is what I found:\n\nThe client owns it").startswith("The client")


def test_labelled_parses_despite_markdown():
    got = labelled("**RISK:** they own it\n**WHY:** you get nothing\n**FIX:** tie it to payment",
                   ["RISK", "WHY", "FIX"])
    assert got["risk"] == "they own it"
    assert got["fix"] == "tie it to payment"


def test_sentences_and_bullets_are_capped():
    assert len(sentences("One. Two. Three. Four.", 2)) == 2
    assert bullets("- keep the files\n- two rounds\n- portfolio rights", 2) == ["keep the files", "two rounds"]


@pytest.mark.parametrize("raw", [
    '{"items": [{"clause": "1"}]}',
    '```json\n{"items": [{"clause": "1"}]}\n```',
    'Sure! {"items": [{"clause": "1"}]} hope that helps',
])
def test_json_extraction_tolerates_chatter(raw):
    assert parse_json(raw) == {"items": [{"clause": "1"}]}


def test_json_extraction_returns_none_on_garbage():
    assert parse_json("I could not find anything") is None


# --------------------------------------------------------------------------- #
# Deterministic fallbacks: the report is complete even with no model at all
# --------------------------------------------------------------------------- #

def test_every_role_has_a_fallback_without_an_engine():
    a = analyse(load(SAMPLES / "northgate_msa.txt"))
    ov = narrate.overview(None, a)
    assert ov["source"] == "library" and ov["worst"]
    em = narrate.negotiation_email(None, a)
    assert em["source"] == "template" and "Suggested:" in em["body"]
    assert narrate.explain(None, a, a.findings[0]) == a.findings[0].why
    assert narrate.ambiguities(None, a) == []


def test_source_label_names_the_model_that_ran():
    from redpen.llm import LocalLLM

    assert narrate._src(LocalLLM(base_url="http://127.0.0.1:1/v1", model="qwen-2.5-1.5b")) == "qwen-2.5-1.5b"
    assert narrate._src(LocalLLM(base_url="http://127.0.0.1:1/v1", model="gemma-3-1b-it:latest")) == "gemma-3-1b-it"
    assert narrate._src(None) == "library"
