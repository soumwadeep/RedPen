"""Document typing, unfilled blanks, date sanity, and the two new rule sets.

Every pattern in employment.py and nda.py was taken from real paperwork the tool
was run against -- offer letters, an internship agreement and an NDA. The
fixtures here restate that phrasing in synthetic form, because a user's actual
contracts must never end up in a public repository's test suite.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from redpen import doctype
from redpen.engine import analyse
from redpen.ingest import load, load_text
from redpen.rules import NDA_RULES, RULES, counts

SAMPLES = Path(__file__).resolve().parent.parent / "samples"


def doc(name: str):
    return load(SAMPLES / name)


# --------------------------------------------------------------------------- #
# Typing
# --------------------------------------------------------------------------- #

@pytest.mark.parametrize("name,kind", [
    ("northgate_msa.txt", doctype.SERVICES),
    ("lumen_typical.txt", doctype.SERVICES),
    ("bright_harbour_fair.txt", doctype.SERVICES),
    ("offer_letter_internship.txt", doctype.EMPLOYMENT),
    ("nda_one_way.txt", doctype.NDA),
])
def test_documents_are_classified(name, kind):
    c = doc(name)
    got = doctype.classify(c.text)
    assert got.kind == kind, f"{name} -> {got.kind} signals={got.signals}"
    assert got.contractual


def test_an_onboarding_checklist_is_refused_not_reviewed():
    """Instructions are not promises. Scoring one would manufacture findings."""
    text = (
        "Sign NDA: You will receive an NDA that you need to sign and send back to "
        "your reporting manager.\n\n"
        "Setup your email: You must have received the details for your new work "
        "email ID. Set it up in your machine. Use your work email for all work "
        "purposes.\n\n"
        "Send these details to your reporting manager: your full name, your "
        "address, one ID proof soft copy, your bank account details.\n\n"
        "Install these: VS Code, TablePlus, Git.\n"
    )
    a = analyse(load_text("onboarding", text))
    assert not a.doc_type.contractual
    assert a.findings == []
    assert a.score == 0
    assert a.band == "clean"


def test_informal_but_binding_text_is_still_reviewed():
    """No 'agreement' anywhere, but real obligations -- refusing this would be
    the opposite failure to reviewing a checklist."""
    text = (
        "Hi, we will build you a site for 800 dollars and you own it as soon as we "
        "start writing it. Payment is due whenever we feel the work is finished to "
        "our standard.\n\n"
        "If we cancel you get nothing back and you will not show the design "
        "anywhere, and you will not work for anyone else in our market for two "
        "years after we finish.\n\n"
        "You will be liable for anything that goes wrong with our business as a "
        "result of the site, without any limit, and you will pay our legal costs "
        "however the claim arises, no matter whose fault it is.\n"
    )
    a = analyse(load_text("email-deal", text))
    assert a.doc_type.contractual
    assert a.findings, "an informal but binding email must still be reviewed"


def test_rule_counts_cover_all_three_libraries():
    c = counts()
    assert c["total"] == len(RULES) >= 60
    assert c["by_scope"].get("employment", 0) >= 15
    assert c["by_scope"].get("nda", 0) >= 8
    assert c["by_scope"].get("services", 0) >= 15


# --------------------------------------------------------------------------- #
# Scoping: the noise that made the first real run useless
# --------------------------------------------------------------------------- #

def test_freelance_rules_stay_quiet_on_an_offer_letter():
    """Before typing, an internship letter was told it had no deposit clause and
    no late-payment interest -- true, worthless, and sitting next to a real
    finding about its withheld certificates."""
    a = analyse(doc("offer_letter_internship.txt"))
    fired = {f.rid for f in a.findings}
    for noise in ("no-deposit-required", "no-late-payment-interest",
                  "no-suspension-right", "no-acceptance-criteria",
                  "long-payment-terms", "pay-when-paid"):
        assert noise not in fired, f"{noise} should not run on an offer letter"


def test_employment_rules_do_not_run_on_a_services_agreement():
    a = analyse(doc("northgate_msa.txt"))
    fired = {f.rid for f in a.findings}
    assert "unpaid-trial-period" not in fired
    assert "original-documents-held" not in fired


def test_nda_specific_rules_only_fire_on_an_nda():
    nda = {f.rid for f in analyse(doc("nda_one_way.txt")).findings}
    services = {f.rid for f in analyse(doc("northgate_msa.txt")).findings}
    assert "nda-indemnity-hidden" in nda
    assert "nda-indemnity-hidden" not in services


# --------------------------------------------------------------------------- #
# Recall on the two new document types
# --------------------------------------------------------------------------- #

OFFER_MUST_FIRE = [
    "unpaid-trial-period", "original-documents-held", "asymmetric-notice",
    "subjective-performance-termination", "final-settlement-delay",
    "variable-pay-undefined", "ip-covers-all-related-work", "public-sharing-ban",
    "open-ended-duty-scope", "unilateral-amendment", "location-at-discretion",
    "byod-no-allowance", "benefits-excluded", "fixed-hours-control",
    "discretionary-conversion", "no-stipend-payment-date",
    "dates-start-before-letter",
]


def test_offer_letter_catches_every_planted_problem():
    a = analyse(doc("offer_letter_internship.txt"))
    fired = {f.rid for f in a.findings}
    missing = [r for r in OFFER_MUST_FIRE if r not in fired]
    assert not missing, f"missed: {missing}"
    assert a.counts["stop"] >= 4


NDA_MUST_FIRE = [
    "nda-indemnity-hidden", "nda-perpetual-by-definition", "nda-oral-catch-all",
    "nda-no-portfolio-reference", "nda-one-way-injunctive",
    "nda-one-way-assignment", "nda-staff-flowdown-liability",
    "nda-return-destroy-no-carveout", "no-liability-cap-anywhere",
]


def test_nda_catches_every_planted_problem():
    a = analyse(doc("nda_one_way.txt"))
    fired = {f.rid for f in a.findings}
    missing = [r for r in NDA_MUST_FIRE if r not in fired]
    assert not missing, f"missed: {missing}"


def test_the_survive_until_public_trick_is_not_fooled():
    """"Confidential until everything is public" is perpetual in disguise, and a
    keyword search for 'perpetual' or 'indefinitely' walks straight past it."""
    a = analyse(doc("nda_one_way.txt"))
    hit = next(f for f in a.findings if f.rid == "nda-perpetual-by-definition")
    assert "publicly known" in hit.evidence[0].quote
    # and it must not also claim there is no term at all
    assert "nda-no-term-end" not in {f.rid for f in a.findings}


# --------------------------------------------------------------------------- #
# Date sanity -- found on a real letter, not invented
# --------------------------------------------------------------------------- #

def test_start_date_before_the_letter_is_flagged():
    a = analyse(doc("offer_letter_internship.txt"))
    hit = next(f for f in a.findings if f.rid == "dates-start-before-letter")
    assert hit.severity == 3
    quotes = " ".join(e.quote.lower() for e in hit.evidence)
    assert "29 june 2026" in quotes and "3 july 2025" in quotes


def test_end_before_start_is_flagged():
    text = (
        "INTERNSHIP AGREEMENT\n\nDate: 10 March 2026\n\n1. Start Date: 1 June 2026. "
        "The intern shall perform the services as assigned by the mentor.\n\n"
        "2. End Date: 1 January 2026. Either party may terminate on 30 days notice "
        "and the stipend shall be paid on or before the 7th of each month.\n\n"
        "3. Confidentiality obligations continue for 2 years after the end date and "
        "the intern retains general skills. Payment is governed by the laws of India.\n"
    )
    a = analyse(load_text("backwards", text))
    assert "dates-impossible-order" in {f.rid for f in a.findings}


def test_consistent_dates_are_not_flagged():
    a = analyse(doc("bright_harbour_fair.txt"))
    assert not any(f.rid.startswith("dates-") for f in a.findings)


@pytest.mark.parametrize("raw,expected", [
    ("29/06/2023", (2023, 6, 29)),
    ("29 /06/2023", (2023, 6, 29)),
    ("3-Jul-2022", (2022, 7, 3)),
    ("26th Oct 2023", (2023, 10, 26)),
    ("08 July 2024", (2024, 7, 8)),
    ("17 November 2024", (2024, 11, 17)),
    ("nonsense", None),
])
def test_date_parser_handles_real_formats(raw, expected):
    from redpen.engine import _parse_date
    assert _parse_date(raw) == expected


# --------------------------------------------------------------------------- #
# Unfilled blanks
# --------------------------------------------------------------------------- #

def test_placeholders_are_counted_and_named():
    text = ("This Agreement is made on [Effective Date] between [Client Legal Name] "
            "and the Freelancer. Fees of INR [Amount] payable within [7/15] calendar "
            "days, with ___% advance. Venue shall be [city, state].")
    b = doctype.find_placeholders(text)
    assert b.total >= 4
    assert "Effective Date" in b.fields
    assert "Amount" in b.fields
    assert any("_" in s for s in b.samples)


def test_a_bracketed_number_is_a_choice_not_a_blank():
    """"[5] business days" and "[7/15] calendar days" are decided values."""
    b = doctype.find_placeholders("Review within [5] business days, payable in [7/15] days.")
    assert b.total == 0


def test_blank_triggers_are_demoted_and_tagged():
    """An unfilled venue is advice to finish the form, not a hostile term.
    Reporting '[city, state] has exclusive jurisdiction' at the same level as
    'Wilmington, Delaware' is how a report stops being trustworthy."""
    a = analyse(doc("nda_one_way.txt"))
    venue = next((f for f in a.findings if f.rid == "far-venue-arbitration"), None)
    assert venue is not None
    assert venue.placeholder is True
    assert venue.severity == 1


def test_expense_safety_clause_is_not_reported_as_denial():
    """"The freelancer will not incur expenses without approval" is prudent, not
    a denial of reimbursement -- the old pattern matched 'no' inside 'not'."""
    text = (
        "1. FEES. The Client shall pay the Freelancer INR 50,000 within 15 days of "
        "invoice, and a deposit of 40% is due on signature. Overdue invoices accrue "
        "interest at 1.5% per month and the Freelancer may suspend work while unpaid.\n\n"
        "2. EXPENSES. Pre-approved third-party costs are payable by the Client in "
        "addition to the fees. The Freelancer will not incur new expenses on the "
        "Client's behalf without approval.\n\n"
        "3. SCOPE. Deliverables and acceptance criteria are in Schedule A, and each "
        "party's liability shall not exceed the fees paid.\n"
    )
    a = analyse(load_text("prudent", text))
    assert "expenses-denied" not in {f.rid for f in a.findings}


# --------------------------------------------------------------------------- #
# The precision guarantee still holds
# --------------------------------------------------------------------------- #

def test_fair_services_contract_is_still_clean():
    a = analyse(doc("bright_harbour_fair.txt"))
    assert a.findings == [], [f.rid for f in a.findings]


def test_hostile_services_contract_is_still_caught():
    a = analyse(doc("northgate_msa.txt"))
    assert a.score >= 90 and a.counts["stop"] >= 8


def test_every_new_rule_is_documented():
    for r in RULES:
        assert r.why.strip() and r.fix.strip() and r.ask.strip(), r.rid
        assert r.applies_to in {"any", "services", "employment", "nda"}, r.rid


def test_every_rule_pattern_compiles():
    from redpen.rules import rx

    for r in RULES:
        patterns = list(r.any_of) + [p for g in r.all_of for p in g] + list(r.none_of)
        for pat in patterns:
            try:
                rx(pat)
            except Exception as exc:
                pytest.fail(f"{r.rid}: bad pattern {pat!r} -> {exc}")
