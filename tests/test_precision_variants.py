"""Precision across many fair drafts, not one.

Both review comments landed on the same gap: the fair-contract claim rested on a
single document, which is an anecdote. A rule set can look perfectly precise on
one file it was tuned against and be noisy on the next well-drafted agreement.

Each case here is a fair draft in a different trade and jurisdiction, and each is
paired with a one-word-smaller near-miss: the same document with a single clause
swapped for the hostile version. Silence on the fair draft and exactly one named
finding on the near-miss together prove the rule is discriminating, not asleep.
"""

from __future__ import annotations

import pytest

from redpen.engine import analyse
from redpen.ingest import load_text

# --------------------------------------------------------------------------- #
# Fair drafts -- these must produce no findings at all
# --------------------------------------------------------------------------- #

FAIR: dict[str, str] = {
    "uk-sole-trader-consulting": """
1. APPOINTMENT. The Consultant is engaged as an independent contractor on a
non-exclusive basis. The Consultant decides how, when and where the Services are
performed and is not subject to the Client's internal policies or supervision.

2. FEES. The Client shall pay 4,000 GBP per month, exclusive of VAT where
applicable. A deposit of 30% is due on signature. Invoices are payable within 14
days and overdue invoices accrue interest at 1.5% per month. The Consultant may
suspend work on 14 days' written notice while an undisputed invoice is unpaid.

3. SCOPE. The Services are those listed in Schedule 1. Either party may raise a
written change request stating the effect on fee and schedule; changes take
effect on written acceptance.

4. INTELLECTUAL PROPERTY. Title in the Deliverables passes to the Client on
payment in full. The Consultant retains its pre-existing materials and tooling
and grants the Client a perpetual licence to use them as embedded in the
Deliverables. The Consultant may describe the work in its portfolio after public
launch.

5. LIABILITY. Each party's total liability shall not exceed the fees paid in the
12 months before the claim, and neither party is liable for indirect or
consequential loss or lost profits.

6. TERMINATION. Either party may terminate on 30 days' written notice. The Client
pays for all work performed to the termination date. Renewal requires written
agreement of both parties.

7. CONFIDENTIALITY. Confidential Information means information disclosed in
writing and marked confidential. It excludes general skills, knowledge and
experience. Obligations continue for 5 years after termination.

8. LAW. This Agreement is governed by the laws of England and Wales and the
parties submit to the courts there, save that either party may use the small
claims procedure.
""",

    "india-developer-sow": """
1. SCOPE OF WORK. The Developer shall build the application described in Annexure
A, which lists each Deliverable with objective acceptance criteria. The engagement
is non-exclusive and the Developer determines the method and hours of work.

2. CHARGES AND PAYMENT. Total charges are INR 6,00,000 plus GST as applicable,
billed separately. 40% is payable on signature, 40% on acceptance of the beta and
the balance on go-live. Each invoice is payable within 15 days. Payment is not
contingent on the Client receiving funds from any third party. Overdue invoices
attract interest at 12% per annum and the Developer may pause work after 21 days
unpaid.

3. ACCEPTANCE. The Client shall test each Deliverable against the criteria in
Annexure A within 10 business days. Deliverables not rejected in writing with
stated reasons in that period are deemed accepted.

4. REVISIONS AND CHANGES. The charges include two rounds of consolidated
feedback per Deliverable. Further rounds are billed at INR 1,200 per hour. Either
party may raise a change request, which takes effect on written agreement of the
fee and date impact.

5. INTELLECTUAL PROPERTY. On payment in full, the Deliverables vest in the
Client. The Developer's libraries, frameworks, boilerplate and tools remain the
Developer's Background IP, licensed to the Client perpetually and irrevocably for
use with the Deliverables. Source and working files of the Developer's tooling
are not Deliverables. The Developer may showcase non-confidential screenshots
after the product is public.

6. LIABILITY AND INDEMNITY. Each party's aggregate liability is capped at the
fees paid. Neither party is liable for indirect, incidental, special or
consequential loss or lost revenue. The Developer indemnifies the Client only
against third-party claims that the Deliverables infringe IP rights, excluding
claims arising from the Client's own materials or modifications.

7. TERM AND TERMINATION. Either party may terminate on 30 days' written notice.
On termination the Client pays for work performed to that date and retains
Deliverables only on payment.

8. CONFIDENTIALITY AND DATA. Each party protects the other's information marked
confidential for 3 years, excluding information that becomes public without
breach or is independently developed. Personal data is processed only on written
instructions.

9. DISPUTES. Governed by the laws of India; courts at Pune have jurisdiction, and
either party may approach the consumer forum or small causes court where the sum
is below its limit.
""",

    "us-design-studio-msa": """
1. SERVICES. Studio provides design services on a non-exclusive basis as an
independent contractor. Studio controls its own schedule, staff and methods.

2. FEES. Fixed fees are stated in each Statement of Work, exclusive of sales or
use taxes. 50% is due on SOW signature. Invoices are payable within Net 15 days
and are not contingent on Client's receipt of funds from any third party. Late
amounts accrue interest at 1.5% per month and Studio may suspend the project on
10 days' notice while an undisputed invoice is overdue.

3. SCOPE. Each SOW lists Deliverables and acceptance criteria. Additional or
changed work requires a signed change order priced at the rates in Exhibit B.

4. ACCEPTANCE. Client has 10 business days to notify Studio of material
non-conformity in writing. Deliverables not so rejected are deemed accepted.

5. INTELLECTUAL PROPERTY. Ownership of final Deliverables transfers to Client on
payment in full. Studio's templates, brushes, components and process tools remain
Studio's property and are licensed to Client for use within the Deliverables.
Client grants Studio the right to display the work in its portfolio and
awards entries after public launch.

6. LIABILITY. Each party's liability is limited to the fees paid under the
affected SOW in the preceding 12 months. Neither party is liable for indirect,
consequential, incidental, special or punitive damages or lost profits.

7. TERMINATION. Either party may terminate for convenience on 15 days' written
notice, in which case Client pays for all work performed and non-cancellable
commitments.

8. CONFIDENTIALITY. Mutual, covering information marked confidential, for 3
years, excluding general industry knowledge and skills.

9. GOVERNING LAW. Laws of the State where Contractor is located; either party
may bring claims in small claims court.
""",

    "german-translation-contract": """
1. GEGENSTAND. The Translator provides translation services as an independent
contractor on a non-exclusive basis and determines working time and place freely.

2. VERGUEETUNG. Fees per the rate schedule in Annex 1, plus VAT shown
separately. 30% on order confirmation. Invoices are payable within 14 days and
are not contingent on the Client receiving payment from any third party. Overdue
invoices accrue statutory default interest under BGB Section 288. The Translator
may suspend work after a written reminder with 10 days' notice.

3. UMFANG. Each order lists the source text, target language, deadline and the
acceptance criteria in Annex 2. Changes to scope are agreed in writing with an
adjusted fee and deadline.

4. ABNAHME. The Client shall examine and accept or reject within 10 business
days, stating material defects in writing. Deliverables not rejected in that
period are deemed accepted.

5. RECHTE. Usage rights transfer to the Client on payment in full. The
Translator's translation memory, glossaries and terminology databases remain the
Translator's own and are licensed to the Client for the purposes of this
contract. The Translator may reference the Client by name after publication.

6. HAFTUNG. Liability of each party is capped at the fees paid under the
affected order. Neither party is liable for indirect or consequential loss or
lost profit. Liability for breach of confidentiality is not capped.

7. BEENDIGUNG. Either party may terminate on 30 days' written notice. On
termination the Client pays for work performed to that date.

8. VERTRAULICHKEIT. Mutual, covering information marked confidential, for 3
years, excluding knowledge and skill generally held in the profession.

9. RECHT. German law; courts at the Translator's seat have jurisdiction.
""",

    "australia-marketing-retainer": """
1. ENGAGEMENT. The Agency is an independent contractor engaged on a
non-exclusive basis. The Agency decides who performs the work and how.

2. FEES. A monthly retainer of AUD 3,500 exclusive of GST, invoiced in advance,
with a first-month deposit. Payment is due within 7 days and is not contingent
on the Client's receipt of funds from any third party. Overdue amounts accrue
interest at 2% per month and the Agency may suspend deliverables on 10 business
days' written notice while an undisputed amount is unpaid.

3. SCOPE. The retainer covers the activities in Schedule 1. Work outside it is
quoted separately and proceeds only on written approval of the fee and timing.

4. DELIVERABLES. Each deliverable is measured against the criteria in Schedule
1. The Client has 10 business days to give written reasons for rejection;
otherwise the deliverable is deemed accepted.

5. INTELLECTUAL PROPERTY. Ownership of client-facing deliverables transfers on
payment in full. The Agency's models, frameworks and reporting templates remain
the Agency's property and are licensed to the Client. The Agency may show the
work in its portfolio after the campaign goes live.

6. LIABILITY. Each party's liability is limited to the fees paid in the previous
6 months. Neither party is liable for indirect or consequential loss or lost
profits.

7. TERM. Either party may terminate on 30 days' written notice, with payment for
work performed to that date. Renewal is by written agreement and rates are
reviewed at each renewal.

8. CONFIDENTIALITY. Mutual, for information marked confidential, for 3 years
after termination, excluding the Agency's general skills and knowledge.

9. LAW. New South Wales law and jurisdiction; either party may use the NCAT
minor claims list.
""",

    "fair-internship-offer": """
INTERNSHIP AGREEMENT

Date: 4 March 2026

1. The Company engages the Intern as a front-end development intern for a paid
internship. The stipend is INR 25,000 per month, payable on or before the 7th of
the following month, and accrues from day one including the induction period.

2. Working hours are 5 days a week, agreed with the mentor, and the Intern
determines the order and method of assigned tasks. Duties are limited to the
role described in Annexure A; material additions are agreed in writing.

3. The Company provides a laptop and all necessary licences and subscriptions.
The Intern is not required to maintain insurance or to provide original
certificates; certified copies are sufficient and originals are verified and
returned the same day.

4. Work produced by the Intern within the scope of the assignment using Company
resources vests in the Company on payment of the stipend for that period. The
Intern retains general skills and knowledge and may describe the work in general
terms in a portfolio after public launch. Coursework and personal projects remain
the Intern's own.

5. Either party may terminate on 14 days' written notice, and the Company pays
for all days worked to the termination date. No amount is recoverable from the
Intern on termination.

6. Confidentiality obligations are mutual and last 2 years after the internship,
excluding information that becomes public without breach and the Intern's general
professional knowledge.

7. Any conversion to full-time employment is assessed against written criteria
shared at the start and communicated in writing at least 30 days before the
internship ends.

7. Each party's liability arising from the internship is limited to the stipend
paid in the preceding 3 months, and neither party is liable for indirect or
consequential loss. The Company covers the Intern against third-party claims
arising from work performed on instruction.

8. A named HR contact outside the reporting line is available for grievances,
and no adverse action follows a good-faith report. Disputes are governed by the
laws of India and the courts at the Intern's place of work have jurisdiction, save
that either party may use the small causes court.
""",

    "mutual-nda": """
MUTUAL NON-DISCLOSURE AGREEMENT

1. DEFINITIONS. Confidential Information means information disclosed in writing
and marked confidential, or disclosed orally and confirmed in writing within 15
days. It excludes information that is public without breach, already lawfully
held, independently developed, or the recipient's general skills, knowledge and
experience.

2. OBLIGATIONS. Each party protects the other's Confidential Information as
carefully as its own, uses it only for the Purpose, and discloses it only to
those with a need to know who are bound by equivalent terms.

3. COMPELLED DISCLOSURE. Either party may disclose where required by law, given
prompt notice and reasonable cooperation to narrow it.

4. RETURN. On written request each party returns or destroys the other's
Confidential Information, except one archival copy retained under the same
obligations where required by law or automated backup systems.

5. TERM. This Agreement runs for the term of the engagement and the obligations
continue for 3 years afterwards, and indefinitely only for information that is a
trade secret under applicable law.

6. NO GRANT. No licence or right in either party's patents, copyrights or
trade secrets is granted by disclosure. Nothing restricts either party from
performing services for others.

7. PUBLICITY. Neither party names the other in press releases without written
consent, but each may state that a working relationship existed and list the
other as a client or supplier in proposals and credentialing.

8. REMEDIES. Either party may seek injunctive relief for breach of
confidentiality. Neither party indemnifies the other for legal costs, and each
party's liability is limited to direct loss caused by its own breach.

9. ASSIGNMENT. Neither party may assign this Agreement without the other's
written consent, not to be unreasonably withheld.

10. DISPUTES. Governed by the laws of India. The parties shall first negotiate
for 14 days; thereafter the courts at the defendant's principal place of business
have jurisdiction, and either party may use small-claims procedure where the sum
is below its threshold.
""",

    "fixed-fee-web-build": """
1. SERVICES. The Developer builds the website described in Schedule A as an
independent contractor on a non-exclusive basis, controlling method and hours.

2. FEES. A fixed fee of 4,200 EUR plus VAT, invoiced 40% on signature, 40% on
acceptance of the staging site and 20% on launch. Payment is due within 14 days
of each invoice and is not contingent on the Client receiving funds from any
third party. Overdue invoices accrue interest at 1% per month and the Developer
may pause work on 10 days' notice while an undisputed amount is unpaid.

3. SCOPE AND CHANGES. Schedule A lists each Deliverable and its acceptance
criteria. Additional pages, integrations or redesigns are change requests, priced
at 70 EUR per hour and scheduled on written approval. The fee includes two rounds
of consolidated revisions per Deliverable.

4. ACCEPTANCE. The Client has 10 business days to reject in writing with stated
reasons against the criteria; otherwise the Deliverable is deemed accepted and
the invoice falls due.

5. INTELLECTUAL PROPERTY. Ownership of the delivered site transfers on payment in
full. The Developer's starter kits, components and build tooling remain the
Developer's and are licensed to the Client for use with the site. The Developer
may show the site in its portfolio and credit itself in the site footer.

6. CONTENT AND ACCESS. The Client supplies text, images and credentials it has
the right to use, and maintains its own backups. The Developer is not liable for
loss arising from the Client's failure to do so.

7. LIABILITY. Each party's liability is capped at the fees paid. Neither party is
liable for indirect or consequential loss or lost sales. The Developer is
responsible for its own negligence and for fixing confirmed defects for 90 days
after launch at no charge.

8. TERMINATION. Either party may terminate on 14 days' written notice, paying for
work performed and non-cancellable third-party costs to that date.

9. CONFIDENTIALITY. Mutual, covering information marked confidential, for 2
years, excluding general professional skills.

10. LAW. Laws of the Client's country of establishment, and either party may
bring smaller claims in the other's local small-claims court.
""",
}


@pytest.mark.parametrize("name", list(FAIR))
def test_a_fair_draft_in_its_own_trade_produces_no_findings(name):
    a = analyse(load_text(name, FAIR[name]))
    assert a.doc_type.contractual, f"{name} should be recognised as an agreement"
    assert a.findings == [], (
        f"{name} produced false positives: "
        + ", ".join(f"{f.rid}(p{f.pages})" for f in a.findings))
    assert a.score == 0


# --------------------------------------------------------------------------- #
# Near misses -- the same draft with one clause turned hostile
# --------------------------------------------------------------------------- #

NEAR_MISS = [
    ("uk-sole-trader-consulting",
     "2. FEES. The Client shall pay 4,000 GBP per month, exclusive of VAT. "
     "Invoices are payable within 90 days of the Client's approval of the work.",
     "long-payment-terms"),

    ("india-developer-sow",
     "5. INTELLECTUAL PROPERTY. All work product, including all source files and "
     "the Developer's libraries, vests in the Client upon creation whether or not "
     "payment has been made.",
     "ip-vests-on-creation"),

    ("us-design-studio-msa",
     "6. LIABILITY. Studio's liability is unlimited and Studio shall indemnify "
     "Client against any and all claims, losses and costs howsoever arising, "
     "including indirect and consequential loss and lost profits.",
     "unlimited-liability"),

    ("australia-marketing-retainer",
     "3. SCOPE. The Client may change the scope and additional activities at any "
     "time at its sole discretion and the Agency shall perform them within the "
     "retainer.",
     "unilateral-scope"),

    ("fair-internship-offer",
     "3. The Company shall retain the Intern's original degree certificates until "
     "the internship is completed, and a replacement document approved by HR is "
     "required to obtain their return.",
     "original-documents-held"),

    ("mutual-nda",
     "8. REMEDIES. The Discloser may seek injunctive relief without a requirement "
     "to post bond, and the Recipient agrees to keep indemnified against any "
     "losses or damages including reasonable attorneys' fees arising due to "
     "breach by the Recipient.",
     "nda-indemnity-hidden"),

    ("fixed-fee-web-build",
     "2. FEES. The fixed fee is 4,200 EUR inclusive of all taxes. Payment shall be "
     "made when the Client receives the corresponding funds from its end client.",
     "pay-when-paid"),
]


@pytest.mark.parametrize("base,clause,expected", NEAR_MISS,
                         ids=[n[2] for n in NEAR_MISS])
def test_one_hostile_clause_in_a_fair_draft_is_caught(base, clause, expected):
    """Append the hostile version as its own clause and the rule must wake up.

    Appending rather than replacing is deliberate: a fair agreement that also
    contains one bad promise should still be flagged on that promise, which is
    the behaviour a user actually depends on. It also keeps the test honest --
    the surrounding good drafting is still there to be fooled by.
    """
    doc = FAIR[base] + "\n\n99. ADDITIONAL TERM. " + clause + "\n"
    a = analyse(load_text(f"{base}-{expected}", doc))
    fired = {f.rid for f in a.findings}
    assert expected in fired, f"{expected} not caught when appended; fired={sorted(fired)}"


@pytest.mark.parametrize("base", list(FAIR))
def test_appending_nothing_changes_nothing(base):
    """Control: the same document with a harmless extra clause stays clean, so a
    pass above cannot be credited to the mere presence of clause 99."""
    doc = FAIR[base] + "\n\n99. NOTICES. Notices may be given by email to the addresses in Schedule 2.\n"
    a = analyse(load_text(base + "-control", doc))
    assert a.findings == [], [f.rid for f in a.findings]
