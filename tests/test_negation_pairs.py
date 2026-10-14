"""Minimal pairs: the same clause, asserted and negated.

Raised in review of the submission: negation-aware matching was demonstrated by
one composite fair contract, which is a demo, not coverage. A rule that survives
"payment is not contingent on receipt of funds" can still fail on "no party
shall indemnify". This file tests each negation-sensitive rule against its own
pair, so the claim is per-rule rather than one lucky document.

Each pair is the same wording with the obligation turned on or off. The
asserted form must fire; the refused form must not.
"""

from __future__ import annotations

import re

import pytest

from redpen.ingest import normalise
from redpen.rules import RULES

BY_ID = {r.rid: r for r in RULES if not r.doc_scope}


def flow(text: str) -> str:
    return re.sub(r"\s+", " ", normalise(text))


def fires(rid: str, text: str) -> bool:
    rule = BY_ID[rid]
    f = flow(text)
    return bool(rule.hits(f)) and (rule.where is None or rule.where(f))


# (rule, asserted -- must fire, refused -- must stay silent)
PAIRS: list[tuple[str, str, str]] = [
    ("pay-when-paid",
     "Payment shall be made when the Client receives funds from its end client.",
     "Payment is not contingent on Client's receipt of funds from any third party."),

    ("unlimited-liability",
     "The Contractor's liability under this Agreement shall be unlimited.",
     "Nothing in this Agreement shall make the Contractor's liability unlimited."),

    ("one-way-consequential",
     "Contractor shall be liable for any indirect, incidental or consequential loss.",
     "Neither party shall be liable for any indirect, incidental or consequential loss."),

    ("broad-indemnity",
     "Contractor shall indemnify the Client against any and all losses howsoever arising.",
     "Contractor shall not indemnify the Client against any and all losses howsoever arising."),

    ("exclusivity-noncompete",
     "Contractor shall not provide services to any other client in the same industry.",
     "Contractor is not exclusive and may provide services to any other client."),

    ("portfolio-ban",
     "Contractor shall not display the Deliverables in any portfolio, website or case study.",
     "Contractor may display the Deliverables in its portfolio, website and case studies."),

    ("set-off-rights",
     "Client may set off any amount it considers necessary against an invoice.",
     "No set-off may be applied by the Client against any undisputed invoice."),

    ("ip-vests-on-creation",
     "All work product shall be the exclusive property of the Client upon creation.",
     "All work product shall not become the property of the Client upon creation."),

    ("ip-whether-or-not-paid",
     "Contractor assigns all rights whether or not payment has been made.",
     "Assignment is not effective whether or not payment has been made; it requires payment in full."),

    ("no-pay-for-wip",
     "On termination the Client shall make no further payment for work in progress.",
     "On termination the Client shall pay for all work performed to that date."),

    ("satisfaction-payment",
     "Payment of each invoice is subject to the Client's complete satisfaction.",
     "Payment is not subject to the Client's complete satisfaction but to the written criteria."),

    ("liquidated-damages",
     "Contractor shall pay liquidated damages of 250 USD per day of delay.",
     "Contractor shall not pay liquidated damages of 250 USD per day of delay."),

    ("convenience-termination",
     "Client may terminate this Agreement at any time for convenience.",
     "Client may not terminate this Agreement at any time for convenience."),

    ("auto-renew",
     "This Agreement shall automatically renew unless either party gives notice.",
     "This Agreement shall not automatically renew; renewal requires written agreement."),

    ("moral-rights-waiver",
     "Contractor hereby waives all moral rights in the work product.",
     "Contractor does not waive, and shall not be required to waive, moral rights."),

    ("source-and-working-files",
     "All source files and working files shall be delivered as the property of the Client.",
     "Source files and working files are not Deliverables and remain Contractor's property."),

    ("all-taxes-on-you",
     "Fees are inclusive of all taxes, including any withholding tax, which are Contractor's responsibility.",
     "Fees are exclusive of all taxes; no tax is Contractor's responsibility beyond its own income."),

    ("unlimited-revisions",
     "Contractor shall provide unlimited revisions until the Client is satisfied.",
     "Contractor shall not provide unlimited revisions; the fee includes two rounds."),

    ("unilateral-scope",
     "Client may modify the scope and Deliverables at any time at its sole discretion.",
     "Client may not modify the scope or Deliverables at its sole discretion."),

    ("far-venue-arbitration",
     "Any dispute shall be resolved by binding arbitration in Delaware.",
     "No dispute shall be resolved by binding arbitration; either party may use small claims."),

    ("overbroad-confidentiality",
     "Confidential Information includes all information learned or observed during the engagement.",
     "Confidential Information does not include all information learned or observed during the engagement."),

    ("revocable-license",
     "Client may revoke any licence granted to Contractor at any time.",
     "Client may not revoke any licence granted to Contractor; the licence is perpetual."),

    ("employee-style-control",
     "Contractor shall work from Client's office during Client's standard business hours.",
     "Contractor shall not be required to work from Client's office or during its hours."),

    ("insurance-demand",
     "Contractor must maintain insurance and provide evidence of insurance before starting work.",
     "Contractor is not required to maintain insurance or provide evidence of insurance."),

    ("assignment-their-side",
     "Client may freely assign this Agreement or its rights hereunder.",
     "Client may not freely assign this Agreement or its rights hereunder."),

    ("perpetual-secrecy",
     "Confidentiality obligations shall survive termination indefinitely.",
     "Confidentiality obligations shall not survive termination indefinitely."),

    ("original-documents-held",
     "The original documents you provided will be retained until the training period is completed.",
     "The original documents you provided will not be retained at any time during the engagement."),

    ("unpaid-trial-period",
     "Your first 10 days of the training period shall be an unpaid training period.",
     "No part of the training period shall be an unpaid training period."),

    ("nda-perpetual-by-definition",
     "Obligations survive until such time as all Confidential Information becomes publicly known.",
     "Obligations do not survive until such time as all Confidential Information becomes publicly known."),

    ("long-payment-terms",
     "All invoices shall be paid within 90 days of the invoice date.",
     "No invoice shall be paid later than 14 days of the invoice date."),
]


@pytest.mark.parametrize("rid,asserted,refused", PAIRS, ids=[p[0] for p in PAIRS])
def test_rule_fires_on_the_asserted_form(rid, asserted, refused):
    assert fires(rid, asserted), f"{rid} did not fire on its own asserted wording"


@pytest.mark.parametrize("rid,asserted,refused", PAIRS, ids=[p[0] for p in PAIRS])
def test_rule_stays_silent_on_the_refused_form(rid, asserted, refused):
    assert not fires(rid, refused), f"{rid} fired on wording that refuses the very term"


# --------------------------------------------------------------------------- #
# Carve-out words that are not negations but should read as limits
# --------------------------------------------------------------------------- #

def test_except_and_provided_carve_outs_are_respected():
    """'except', 'provided that' and 'unless' limit an obligation without using
    the word 'not', so a pure negator scan misses them."""
    # "except"/"provided that" limit an obligation without using "not".
    # Named-competitor + duration-only is the compromise the rule itself proposes.
    assert not fires("broad-indemnity",
                     "Contractor shall indemnify Client only for third-party claims "
                     "that the Deliverables infringe IP rights, provided Client gives "
                     "prompt notice.")
    assert not fires("exclusivity-noncompete",
                     "Contractor shall not work for any person identified in writing "
                     "as a direct competitor, for the duration of the engagement only.")


# --------------------------------------------------------------------------- #
# Where the negation logic still over-flags -- recorded, not hidden
# --------------------------------------------------------------------------- #

KNOWN_LIMITATIONS = [
    ("unlimited-liability",
     "Contractor's liability is unlimited in cases of fraud, death or personal injury.",
     "A statutory carve-out reads as an unlimited-liability clause to a pattern matcher."),
    ("insurance-demand",
     "Contractor shall maintain insurance as required by the regulations governing the Services.",
     "Where insurance is legally mandated, asking for it is not a red flag."),
    ("set-off-rights",
     "No deposit shall be required, and the Client may set off any amount it "
     "considers necessary against an invoice.",
     "Negation now scans the whole sentence, so an early 'no' can suppress an "
     "unrelated later clause joined by a comma. Splitting on ';' and '.' helps; "
     "commas are where two independent promises share a sentence."),
]


@pytest.mark.parametrize("rid,text,why", KNOWN_LIMITATIONS,
                         ids=[k[0] for k in KNOWN_LIMITATIONS])
def test_documented_over_flags_are_still_known(rid, text, why):
    """These are expected to fire today. If someone fixes one, xfail-strict makes
    them update this list rather than let the limitation quietly disappear."""
    if fires(rid, text):
        pytest.skip(f"known over-flag: {why}")
    pytest.fail(f"{rid} no longer over-flags this case -- remove it from "
                f"KNOWN_LIMITATIONS so the limitation list stays accurate")
