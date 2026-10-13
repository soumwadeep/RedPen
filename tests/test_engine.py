"""The claim RedPen makes to a paying user is: it catches the traps, and it does
not cry wolf. Both directions are tested, plus the auditability guarantee that
every quoted piece of evidence really exists in the document.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from redpen.engine import analyse
from redpen.ingest import DocumentTooShort, load, load_text, segment
from redpen.rules.catalog import RULES, Rule

SAMPLES = Path(__file__).resolve().parent.parent / "samples"


def doc(name: str):
    return load(SAMPLES / name)


# --------------------------------------------------------------------------- #
# Recall: what must be caught
# --------------------------------------------------------------------------- #

HOSTILE_MUST_FIRE = [
    "ip-vests-on-creation", "ip-whether-or-not-paid", "source-and-working-files",
    "moral-rights-waiver", "portfolio-ban", "pay-when-paid", "long-payment-terms",
    "satisfaction-payment", "liquidated-damages", "set-off-rights",
    "all-taxes-on-you", "unlimited-liability", "one-way-consequential",
    "broad-indemnity", "exclusivity-noncompete", "post-term-restraint",
    "employee-style-control", "unilateral-scope", "unlimited-revisions",
    "convenience-termination", "no-pay-for-wip", "auto-renew",
    "far-venue-arbitration", "perpetual-secrecy", "overbroad-confidentiality",
    "no-liability-cap-anywhere", "no-deposit-required",
    "no-late-payment-interest", "no-preexisting-tools-carve-out",
    "no-acceptance-criteria", "no-suspension-right",
]


@pytest.fixture(scope="module")
def hostile():
    return analyse(doc("northgate_msa.txt"))


def test_hostile_contract_fires_every_planted_trap(hostile):
    fired = {f.rid for f in hostile.findings}
    missing = [rid for rid in HOSTILE_MUST_FIRE if rid not in fired]
    assert not missing, f"these traps were missed: {missing}"


def test_hostile_contract_scores_high(hostile):
    assert hostile.score >= 90
    assert hostile.band == "high"
    assert hostile.counts["stop"] >= 8


def test_absence_rules_are_marked_as_absent_not_quoted(hostile):
    for f in hostile.findings:
        if f.rid in ("no-liability-cap-anywhere", "no-late-payment-interest"):
            assert f.missing or f.denied, f"{f.rid} should be an absence finding"


def test_express_refusal_is_distinguished_from_silence(hostile):
    """'No deposit shall be made' is worse than no deposit clause at all."""
    denied = {f.rid for f in hostile.findings if f.denied}
    assert "no-deposit-required" in denied


# --------------------------------------------------------------------------- #
# Precision: what must NOT be caught
# --------------------------------------------------------------------------- #

def test_fair_contract_produces_no_findings():
    a = analyse(doc("bright_harbour_fair.txt"))
    assert a.findings == [], "false positives: " + ", ".join(f.rid for f in a.findings)
    assert a.score == 0 and a.band == "clean"


def test_negated_language_does_not_fire():
    """Mentions of a trap phrase in order to refuse it are not findings."""
    text = (
        "1. PAYMENT. Client shall pay the fee within 14 days of invoice. "
        "Payment is not contingent on Client's receipt of funds from any third "
        "party, and no set-off may be applied against an undisputed invoice. "
        "There is no exclusivity: Contractor may work for any other client.\n\n"
        "2. INTELLECTUAL PROPERTY. Title passes to Client upon payment in full. "
        "Contractor's tools, source files and working files are not Deliverables "
        "and remain Contractor's property as Background IP, licensed to Client "
        "under a perpetual and irrevocable licence.\n\n"
        "3. GENERAL. Contractor waives moral rights only to the extent necessary "
        "for Client to use the Deliverables as intended and retains the right to "
        "be credited. Contractor may show the work in its portfolio. Either party "
        "may terminate on 30 days' written notice and Client shall pay for all "
        "work performed to that date. Neither party is liable for indirect or "
        "consequential loss or lost profits; each party's liability shall not "
        "exceed the fees paid. A deposit of 40% is due on signature and overdue "
        "invoices accrue interest at 1.5% per month, and Contractor may suspend "
        "work while unpaid. Acceptance criteria are in Schedule A and Deliverables "
        "not rejected in writing within 10 days are deemed accepted. "
        "Confidential Information means information marked confidential and "
        "excludes Contractor's general skills; obligations last 5 years.\n"
    )
    a = analyse(load_text("negation-probe", text))
    assert a.findings == [], "false positives: " + ", ".join(f.rid for f in a.findings)


def test_realistic_middle_contract_sits_between_the_extremes(hostile):
    typical = analyse(doc("lumen_typical.txt"))
    fair = analyse(doc("bright_harbour_fair.txt"))
    assert fair.score < typical.score < hostile.score
    assert typical.counts["stop"] >= 1
    assert {"ip-vests-on-creation", "unlimited-revisions", "one-way-consequential"} <= {
        f.rid for f in typical.findings
    }


def test_role_synonyms_are_understood():
    """A contract that calls the freelancer 'Supplier' is the same contract."""
    text = (
        "1. IP. All Work Product of the Supplier shall become the property of the "
        "Customer upon creation, whether or not payment has been made, and the "
        "Supplier assigns all right title and interest accordingly.\n\n"
        "2. PAYMENT. The Customer shall pay each invoice within 90 days of receipt "
        "and only when the Customer receives funds from its own end customer.\n\n"
        "3. LIABILITY. The Supplier shall indemnify the Customer against any and "
        "all claims, losses and costs howsoever arising, and the Supplier's "
        "liability is unlimited.\n"
    )
    a = analyse(load_text("supplier-terms", text))
    fired = {f.rid for f in a.findings}
    assert {"ip-vests-on-creation", "pay-when-paid", "unlimited-liability"} <= fired


# --------------------------------------------------------------------------- #
# Auditability -- the guarantee that makes the report checkable
# --------------------------------------------------------------------------- #

def test_every_evidence_quote_exists_in_the_source(hostile):
    from redpen.ingest import normalise
    import re
    doc_flow = re.sub(r"\s+", " ", normalise(hostile.contract.text))
    for f in hostile.findings:
        for e in f.evidence:
            core = e.quote.strip("… ").strip()
            # Quotes are padded with context; the centre must be verbatim.
            assert core[:40] in doc_flow, f"{f.rid}: fabricated evidence {core[:60]!r}"


def test_findings_cite_a_real_clause(hostile):
    ids = {c.cid for c in hostile.contract.clauses}
    for f in hostile.findings:
        for e in f.evidence:
            assert e.cid in ids
            assert e.page >= 1


# --------------------------------------------------------------------------- #
# Ingest
# --------------------------------------------------------------------------- #

def test_clause_numbering_is_detected():
    c = doc("northgate_msa.txt")
    assert c.clause_count >= 10
    assert [cl.number for cl in c.clauses][:3] == ["1", "2", "3"]
    assert c.clauses[0].heading.lower().startswith("engagement")


def test_paragraph_fallback_when_numbering_is_absent():
    text = ("We will build you a website for 800 dollars and you own it as soon as "
            "we start writing it, payment is due whenever we feel the work is "
            "finished to our standard.\n\n"
            "If we cancel the project you get nothing back and you may not show "
            "the design anywhere, and you may not work for anyone else in our "
            "market for two years after we finish, and we can change the brief "
            "whenever we like at no extra cost to us.\n\n"
            "You will be liable for anything that goes wrong with our business as "
            "a result of the site, without any limit, and you will pay our legal "
            "costs however the claim arises, no matter whose fault it is.\n")
    c = load_text("informal", text)
    assert c.clause_count >= 2
    assert "paragraph" in " ".join(c.warnings).lower() or c.clause_count >= 3
    a = analyse(c)
    assert a.findings, "an unnumbered agreement should still be reviewable"


@pytest.mark.parametrize("bad", ["", "too short to review"])
def test_refuses_documents_it_cannot_read(bad):
    with pytest.raises(DocumentTooShort):
        load_text("empty", bad)


def test_page_numbers_survive_pdf_round_trip():
    pdf = SAMPLES / "northgate_msa.pdf"
    if not pdf.exists():
        pytest.skip("run samples/make_pdfs.py first")
    c = load(pdf)
    assert c.pages >= 2, "sample should span pages"
    late = [cl for cl in c.clauses if int(cl.number) >= 6]
    assert any(cl.page > 1 for cl in late), "page attribution collapsed"


# --------------------------------------------------------------------------- #
# The rule library itself
# --------------------------------------------------------------------------- #

def test_rule_ids_are_unique():
    ids = [r.rid for r in RULES]
    assert len(ids) == len(set(ids))


def test_every_rule_is_fully_documented():
    for r in RULES:
        assert r.why.strip(), r.rid
        assert r.fix.strip(), r.rid
        assert r.ask.strip(), r.rid
        assert 1 <= r.severity <= 3, r.rid
        assert r.any_of or r.all_of, r.rid


def test_user_rules_merge_without_touching_code(tmp_path):
    import json

    rule = {
        "id": "no-usage-rights-scope",
        "title": "Broadcast rights undefined",
        "category": "ip",
        "severity": 2,
        "why": "A licence to use your edit in perpetuity across all media is a "
               "different price than a 12 month single-platform run.",
        "fix": "Usage is limited to one platform for 12 months; further usage is "
               "priced per the rate card.",
        "ask": "Which platforms and for how long? That changes the fee.",
        "any_of": ["all media", "any media now known or hereafter devised",
                   "perpetual licen"],
        "all_of": [["usage", "licen", "rights"]],
    }
    (tmp_path / "video.json").write_text(json.dumps([rule]))

    from redpen.rules import all_rules, load_user_rules

    extra = load_user_rules(tmp_path)
    assert [r.rid for r in extra] == ["no-usage-rights-scope"]
    combined = all_rules(extra)
    assert any(r.rid == "no-usage-rights-scope" for r in combined)
    assert len(combined) == len(RULES) + 1

    text = (
        "1. LICENCE. Client is granted a perpetual licence to use the edit in any "
        "media now known or hereafter devised, throughout the universe.\n\n"
        "2. FEES. The fee covers the edit only.\n\n"
        "3. CREDIT. Contractor shall invoice on completion and be paid within 14 "
        "days.\n"
    )
    a = analyse(load_text("edit", text), extra_rules=extra)
    assert any(f.rid == "no-usage-rights-scope" for f in a.findings)


def test_broken_user_rule_is_reported_not_fatal(tmp_path):
    (tmp_path / "bad.json").write_text("{not json")
    from redpen.rules import load_user_rules

    rules = load_user_rules(tmp_path)
    assert len(rules) == 1
    assert rules[0].severity == 0
    assert "Could not read" in rules[0].title


def test_library_size_is_a_feature():
    assert len(RULES) >= 30
