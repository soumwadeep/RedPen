"""The red-flag library.

This is the part of RedPen that does the *judging*, and it is deliberately not
a model. Every rule is a declarative pattern set over normalised clause text,
which means three things a general-purpose API cannot offer:

  * a finding always cites the exact words that fired, so the user can check it;
  * the same contract always produces the same report, so it can be reviewed;
  * the library is editable -- a user can add a rule for their own trade in
    twenty lines of Python, and a lawyer can audit the whole set.

The language model never decides what is dangerous. It only explains, in the
context of this contract, what a rule already found, and drafts the email.

Matching vocabulary
-------------------
``any_of``   list of alternative patterns; at least one must match.
``all_of``   list of alternative groups; every group must match.
``none_of``  if any matches, the rule does not fire (a local safe harbour).
``where``    optional python callable for numeric/structural checks.

Severity is what the score is built from:
  3 = do not sign like this      2 = fix before signing
  1 = ask, cheap to win          0 = note only
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

# A phrase only counts as a red flag when it is asserted, not when it is
# mentioned in order to be refused. "Payment is not contingent on Client's
# receipt of funds" contains the words of the pay-when-paid trap and must not
# fire; "No deposit shall be made" contains the words of a deposit term and must
# still fire, but as a refusal. Negation is therefore checked per hit, and only
# against the primary phrase (any_of), never against context groups -- in
# "shall not work for any competitor" the competitor phrase is not itself
# negated, the obligation around it is.
NEGATIVE = re.compile(r"\b(?:no|not|without|never|neither|nor|nil)\b", re.I)


def negated_at(text: str, at: int, window: int = 52) -> bool:
    """Look back through the current sentence for a negator."""
    seg = text[:at]
    for sep in (".", ";"):
        i = seg.rfind(sep)
        if i > 0:
            seg = seg[i + 1:]
    return bool(NEGATIVE.search(seg[-window:]))


# Real agreements call the freelancer "Contractor", "Designer", "Supplier",
# "Service Provider", "Party B" -- and the buyer "Client", "Company", "Customer"
# or "Purchaser". A library hard-wired to one word silently misses the rest, so
# the words *contractor* and *client* written into a pattern below are expanded
# to every role synonym at compile time.
TERMS = {
    "contractor": (r"(?:contractors?|designers?|developers?|engineers?|writers?|"
                   r"consultants?|freelancers?|workers?|employees?|suppliers?|"
                   r"vendors?|subcontractors?|service providers?|"
                   r"independent contractors?|party b)"),
    "client": (r"(?:clients?|companies|customers?|purchasers?|buyers?|"
               r"commissioners?|end clients?|company|party a)"),
}
_EXPANDED: dict[str, str] = {}


def expand(pat: str) -> str:
    if pat in _EXPANDED:
        return _EXPANDED[pat]
    out = pat
    for word, repl in TERMS.items():
        out = re.sub(rf"\b{word}\b", repl, out)
    _EXPANDED[pat] = out
    return out


_COMPILED: dict[str, re.Pattern] = {}


def rx(pat: str) -> re.Pattern:
    key = expand(pat)
    p = _COMPILED.get(key)
    if p is None:
        p = re.compile(key)
        _COMPILED[key] = p
    return p


@dataclass
class Rule:
    rid: str
    title: str
    category: str            # money | ip | risk | control | exit | terms
    severity: int
    why: str                 # plain English, written to a freelancer
    fix: str                 # counter-clause language they can paste
    ask: str                 # the line that goes in the negotiation email
    any_of: list[str] = field(default_factory=list)
    all_of: list[list[str]] = field(default_factory=list)
    none_of: list[str] = field(default_factory=list)
    where: object | None = None
    doc_scope: bool = False  # True = checked against the whole agreement
    applies_to: str = "any"  # any | services | employment | nda

    def hits(self, flow: str) -> list[tuple[int, int]]:
        """Spans of the asserted offending language, negated mentions removed.

        ``all_of`` context groups are checked but not span-reported: in "shall
        not work for any competitor" the competitor phrase is not itself
        negated, the obligation wrapped around it is.
        """
        if not self.any_of and not self.all_of:
            return []
        if any(rx(p).search(flow) for p in self.none_of):
            return []
        spans: list[tuple[int, int]] = []
        for pat in self.any_of:
            for m in rx(pat).finditer(flow):
                if negated_at(flow, m.start()):
                    continue
                lo = m.start(1) if m.lastindex else m.start(0)
                hi = m.end(1) if m.lastindex else m.end(0)
                spans.append((lo, hi))
        if self.any_of and not spans:
            return []
        for group in self.all_of:
            if not any(rx(p).search(flow) for p in group):
                return []
        return spans

    def matches(self, flow: str) -> bool:
        if self.doc_scope:
            return False
        return bool(self.hits(flow))


# --------------------------------------------------------------------------- #
# Numeric helpers used by a few rules
# --------------------------------------------------------------------------- #

_DAYS = re.compile(r"within\s+(\d{1,3})\s*(?:\(?\s*\d*\s*\)?\s*)?(?:business\s+|calendar\s+)?days")
_NOTICE = re.compile(r"(\d{1,3})\s*(?:business\s+)?days'?[\s,]*(?:prior\s+)?(?:written\s+)?notice")


def net_days(flow: str) -> list[int]:
    """Day counts sitting in a payment context, so 90 in a warranty clause is
    not mistaken for Net 90."""
    hits = []
    for m in re.finditer(r"[^.;]{0,90}within\s+(\d{1,3})\s*(?:business\s+|calendar\s+)?days[^.;]{0,90}", flow):
        window = m.group(0)
        if re.search(r"pay|invoice|payment|remit|settle|due", window):
            hits.append(int(m.group(1)))
    return hits


def max_net_days(flow: str) -> int:
    days = net_days(flow)
    return max(days) if days else 0


def longest_notice(flow: str) -> int:
    ns = [int(m.group(1)) for m in _NOTICE.finditer(flow)]
    return max(ns) if ns else 0


def over(mech: int, threshold: int):
    return lambda flow, m=mech, t=threshold: m(flow) > t


def under(mech: int, threshold: int):
    return lambda flow, m=mech, t=threshold: m(flow) > 0 and m(flow) < t


# --------------------------------------------------------------------------- #
# Catalogue
# --------------------------------------------------------------------------- #

RULES: list[Rule] = [

    # ---------------------------------------------------------------- ip ---- #
    Rule(
        rid="ip-vests-on-creation",
        title="You lose the work the moment you make it",
        category="ip", severity=3,
        any_of=[r"upon (the )?creation", r"as and when (?:it|they) (?:is|are) created",
                r"automatically (?:vest|become)", r"shall (?:be|vest) .*property .*(?:client|company)"],
        all_of=[[r"work product", r"deliverable", r"materials?", r"output"]],
        none_of=[r"upon (?:full )?payment", r"subject to (?:full )?payment"],
        why=("Ownership transfers while you still hold the invoice. If payment "
             "is late or the deal is cancelled mid-project, you have already "
             "given away work you were never paid for -- and reusing it is "
             "then their copyright claim, not yours."),
        fix=("Title to each Deliverable passes to Client only upon Client's "
             "receipt of payment in full for that Deliverable. Until then the "
             "Deliverable remains Contractor's property and Client holds an "
             "expiring licence to use it for internal review."),
        ask=("Can we move the IP transfer to 'on payment in full for that "
             "deliverable'? I'm comfortable either way, I just can't carry "
             "unpaid ownership."),
    ),
    Rule(
        rid="ip-whether-or-not-paid",
        title="Assignment survives non-payment",
        category="ip", severity=3,
        any_of=[r"whether or not payment", r"regardless of (?:any )?payment",
                r"notwithstanding (?:any )?non-?payment", r"prior to (?:any )?payment",
                r"irrespective of payment"],
        why=("This is the same trap stated even more bluntly: payment is not a "
             "condition of the transfer at all. Their non-payment leaves you "
             "with an invoice and no rights."),
        fix="Assignment of Deliverables is expressly conditional on payment in full.",
        ask="Delete 'whether or not payment has been made' -- that phrase makes payment optional.",
    ),
    Rule(
        rid="source-and-working-files",
        title="Source and working files are theirs",
        category="ip", severity=2,
        any_of=[r"source files?", r"working files?", r"native files?", r"project files?",
                r"layered files?", r"sketches", r" drafts", r"intermediate (?:files|work)"],
        all_of=[[r"property of", r"assign", r"deliver", r"hand (?:over|along|with)", r"included"]],
        none_of=[r"not (?:be )?deliverables?", r"separate paid service",
                 r"retain\w* .{0,40}(?:tool|source|working|librar)",
                 r"are excluded", r"excluded from"],
        why=("Handing over the layered PSD, the Figma library or the prompt "
             "set is handing over the toolkit you sell with. Clients often ask "
             "for it, but it should be a paid extra, not a default."),
        fix=("Client receives final exported Deliverables. Contractor's tools, "
             "templates, libraries, macros, source and working files remain "
             "Contractor's property and may be provided as a separate paid "
             "service at the rates in Schedule B."),
        ask="Working files should be a paid add-on. Can we split that out into its own line?",
    ),
    Rule(
        rid="moral-rights-waiver",
        title="Moral rights waived outright",
        category="ip", severity=2,
        any_of=[r"moral rights", r"rights of (?:attribution|integrity)", r"derecognition"],
        all_of=[[r"waive", r"forbear", r"not (?:to )?(?:assert|enforce)", r"extinguish"]],
        none_of=[r"only to the extent necessary", r"except to the extent",
                 r"retains? (?:the )?(?:right to be credited|right of attribution)",
                 r"waives? .{0,40}only in (?:the )?(?:form|manner)"],
        why=("In many countries you cannot transfer authorship, only promise "
             "not to assert it. A blanket waiver can stop you being credited, "
             "and in some jurisdictions it can also stop you objecting when "
             "the work is altered in a way you find damaging."),
        fix=("Contractor waives moral rights only to the extent necessary for "
             "Client to use the Deliverables as intended, and retains the "
             "right to be credited and to object to materially defamatory use."),
        ask="I'd rather keep credit and object only to genuinely damaging edits. Can we narrow that?",
    ),
    Rule(
        rid="portfolio-ban",
        title="You may not show the work",
        category="ip", severity=2,
        any_of=[r"shall not (?:use|display|reference|reproduce|publish)",
                r"no right to display", r"(?:may|shall) not (?:include|mention) .*portfolio",
                r"not.*publicly (?:disclose|show|share)"],
        all_of=[[r"portfolio", r"website", r"_samples", r"samples", r"case stud",
                 r"marketing", r"self-?promot", r"awards"]],
        none_of=[r"with (?:prior |client's )?(?:written )?(?:consent|approval)",
                 r"unless client", r"after (?:the )?(?:launch|public announcement)"],
        why=("For a freelancer the portfolio *is* the sales funnel. A ban on "
             "showing work removes the compounding value of every project and "
             "often quietly conflicts with an NDA clause elsewhere."),
        fix=("Contractor may show reduced-resolution excerpts and the client "
             "name in its portfolio, site and award entries after public "
             "launch, or 90 days after delivery if there is no launch."),
        ask="Can I keep portfolio rights once the project is public? That's how I get my next client.",
    ),

    # ------------------------------------------------------------- money ---- #
    Rule(
        rid="pay-when-paid",
        title="You get paid only after they do",
        category="money", severity=3,
        any_of=[r"when (?:the )?client receives", r"upon (?:the )?(?:end )?client'?s receipt of (?:funds|payment)",
                r"paid when we (?:are|get) paid", r"after (?:the )?(?:end )?client'?s payment",
                r"receipt of funds from", r"payment.*contingent upon", r"contingent upon (?:the )?(?:end )?client"],
        all_of=[[r"payment", r"pay", r"invoice", r"due"]],
        none_of=[r"payment in full", r"receipt of payment in full",
                 r"title (?:to|of) .{0,30}(?:pass|vest)"],
        why=("You become an unsecured creditor of your client's client. Their "
             "cashflow problem, their disputed invoice, their slow procurement "
             "department all become your unpaid month of work."),
        fix=("Payment is due within the stated period from Contractor's "
             "invoice date and is not contingent on Client's receipt of funds "
             "or approval from any third party."),
        ask="I can't take on my end client's payment risk. Can we make the due date run from my invoice?",
    ),
    Rule(
        rid="long-payment-terms",
        title="Payment terms are too long to survive",
        category="money", severity=2,
        any_of=[r"within\s+\d{1,3}\s*(?:business |calendar )?days"],
        all_of=[[r"pay", r"invoice", r"remit", r"settle", r"due"]],
        where=lambda flow: max_net_days(flow) > 30,
        why=("Net 45 to Net 90 is normal for enterprise buyers and ruinous for "
             "an individual. At Net 60 a two-month project gets paid four "
             "months after it ends, and every late invoice compounds it."),
        fix="Payment terms: 50% deposit on commencement, balance within 15 days of delivery.",
        ask="Can we do a deposit plus Net 15? I'd rather move the money earlier than chase it later.",
    ),
    Rule(
        rid="satisfaction-payment",
        title="Payment is subject to 'satisfaction'",
        category="money", severity=3,
        any_of=[r"to (?:the )?(?:client'?s|their) (?:complete )?satisfaction",
                r"satisfactory to (?:the )?client", r"subject to (?:final )?approval",
                r"payment .*upon acceptance"],
        none_of=[r"(?:acceptance criteria|specification|brief) in (?:schedule|annex|appendix)",
                 r"deemed accepted"],
        why=("A subjective standard with no written criteria means the client "
             "decides after the work whether it was ever good enough. Pair it "
             "with clause language on revisions and the project can never end."),
        fix=("Deliverables are accepted against the written criteria in "
             "Schedule A. Client has 10 business days to give written "
             "rejection reasons; Deliverables not rejected in that window are "
             "deemed accepted and the invoice falls due."),
        ask="What are the written acceptance criteria? I'd rather work to a list than to 'satisfaction'.",
    ),
    Rule(
        rid="liquidated-damages",
        title="Daily penalty for missing a date",
        category="money", severity=3,
        any_of=[r"liquidated damages", r"(?:penalty|damages|charge).{0,40}per day",
                r"for each (?:and every )?day .{0,40}(?:deduct|reduce|late|delay)",
                r"delay (?:penalty|charge)"],
        why=("A fixed daily deduction turns one slipped day into a permanent "
             "cut to the fee, and it usually has no matching bonus for early "
             "delivery. Freelancers rarely have the leverage to absorb it."),
        fix=("Where Contractor delays a milestone by more than 5 business days "
             "for reasons within Contractor's control, Client's sole remedy is "
             "to terminate the affected milestone and pay for work completed."),
        ask="Can we swap the daily penalty for 'client may cancel the milestone'? Unlimited downside isn't something I can price.",
    ),
    Rule(
        rid="set-off-rights",
        title="Client may set off amounts against your fee",
        category="money", severity=2,
        any_of=[r"set[- ]off", r"offset any (?:sum|amount|claim)", r"deduct any (?:sum|amount|damages|cost)"],
        all_of=[[r"invoice", r"fee", r"payment", r"amounts? (?:due|payable)"]],
        why=("Unlocks unilateral payment reduction: any disputed allegation "
             "becomes a deduction you then have to litigate to recover, with "
             "the leverage already inverted."),
        fix=("Client may withhold only the undisputed portion of an invoice and "
             "must state the reason and amount in writing within 7 days. No "
             "set-off against unrelated claims."),
        ask="If anything is ever disputed, can we agree you pay the undisputed part and we sort the rest out?",
    ),
    Rule(
        rid="expenses-denied",
        title="Expenses need prior approval that can be withheld",
        category="money", severity=1,
        any_of=[r"expenses.{0,60}(?:prior written approval|not reimbursed|at (?:your|contractor)'?s? cost)",
                r"\bno\b[^.]{0,40}expense[^.]{0,30}reimburs",
                r"\bnot\b[^.]{0,30}reimbursable[^.]{0,30}expense",
                r"approval (?:may be withheld|is at (?:the )?client'?s discretion)"],
        none_of=[r"incur[^.]{0,45}expense[^.]{0,45}without (?:prior )?approval",
                 r"expenses are payable by (?:the )?client", r"reimburses? reasonable",
                 r"pre-?approved"],
        why=("Fine if true, misleading if it is stated as 'expenses reimbursed' "
             "somewhere else. Stock footage, fonts, plugins and test devices "
             "are usually billed to the project, not absorbed."),
        fix=("Client reimburses reasonable, itemised project expenses over "
             "USD 50 approved in writing in advance; smaller items are "
             "reimbursed on production of receipts."),
        ask="Which expenses are billable, and is there a pre-approval threshold?",
    ),
    Rule(
        rid="all-taxes-on-you",
        title="All taxes pushed onto you",
        category="money", severity=2,
        any_of=[r"(?:all|any) taxes.{0,80}(?:contractor|you)(?:'s)? (?:responsibility|borne|sole)",
                r"including any (?:withholding|sales|gst|vat|service) tax",
                r"gross[- ]up"],
        why=("A fee quoted as inclusive of VAT/GST is a fee cut by the tax. "
             "Cross-border withholding can also mean the client keeps 10-30% "
             "of the invoice and you cannot always reclaim it."),
        fix=("Fees are exclusive of applicable taxes, which Client pays in "
             "addition where it is required to collect or withhold them. "
             "Contractor is responsible only for tax on its own income."),
        ask="Is the fee exclusive of VAT/GST/withholding? I quoted it exclusive.",
    ),

    # -------------------------------------------------------------- risk ---- #
    Rule(
        rid="unlimited-liability",
        title="Your liability is unlimited",
        category="risk", severity=3,
        any_of=[r"liability.{0,40}unlimited", r"unlimited .{0,20}liability",
                r"no limitation on (?:the )?contractor'?s liability",
                r"(?:indemnify|hold harmless).{0,80}(?:any and all|all) (?:losses|claims|liabilities|costs)"],
        none_of=[r"shall not exceed", r"aggregate (?:fees|amount paid)", r"liability.{0,60}capped"],
        why=("On a $4,000 logo you carry uncapped exposure to a client whose "
             "rebrand failure it claims cost $2m. Unlimited liability is the "
             "one term no individual freelancer should accept at any fee."),
        fix=("Each party's total liability is limited to the fees paid or "
             "payable under this Agreement in the 12 months before the claim. "
             "Neither party is liable for indirect, consequential, special or "
             "punitive loss, or for lost profits or revenue."),
        ask="I need a cap at the fees paid. Unlimited liability isn't something I can insure or price.",
    ),
    Rule(
        rid="one-way-consequential",
        title="Consequential damages run one way only",
        category="risk", severity=2,
        any_of=[r"indirect|consequential|incidental|special|punitive|exemplary",
                r"lost (?:sales|revenue|profits?|business|custom|goodwill|orders?)",
                r"damage to .{0,30}(?:business|reputation|goodwill|brand)",
                r"loss of (?:business|revenue|contracts?)"],
        all_of=[[r"contractor shall (?:be liable|indemnify|defend)",
                 r"contractor.{0,40}(?:liable for|will reimburse)",
                 r"contractor'?s (?:liability|responsibility)"]],
        none_of=[r"neither party", r"each party.{0,60}(?:not liable|excluded)",
                 r"mutual.{0,30}waiver"],
        why=("Lost-profits language is how a late deliverable becomes a "
             "seven-figure claim. Exclusions are normally mutual; written one "
             "way, it is a disguised unlimited liability clause."),
        fix="Mutual exclusion: neither party is liable for indirect, incidental, special, consequential or punitive loss, or lost profits.",
        ask="Can that exclusion be mutual? One-sided lost-profits liability is uninsurable for me.",
    ),
    Rule(
        rid="broad-indemnity",
        title="Indemnity with no ceiling or causation test",
        category="risk", severity=2,
        any_of=[r"indemnify", r"hold (?:them |client )?harmless", r"defend .{0,30}(?:from|against)"],
        all_of=[[r"any and all", r"all (?:claims|losses|damages|liabilities|costs)",
                 r"without limitation", r"howsoever arising", r"regardless of (?:the )?(?:cause|fault)"]],
        why=("A defence obligation is immediate: you pay lawyers before anyone "
             "proves fault. 'Regardless of cause' can make you indemnify the "
             "client for harm the client itself caused."),
        fix=("Contractor indemnifies Client against third-party claims that the "
             "Deliverables infringe IP rights, provided Client gives prompt "
             "notice and Contractor controls the defence. No indemnity for "
             "claims arising from Client's modifications, materials or use."),
        ask="Can the indemnity be limited to IP claims and capped at the fees? And not cover things your team caused?",
    ),
    Rule(
        rid="insurance-demand",
        title="Insurance required, cost not covered",
        category="risk", severity=1,
        any_of=[r"(?:shall|must) maintain .{0,40}insurance", r"evidence of insurance",
                r"professional indemnity.{0,60}(?:required|shall)"],
        why=("Legitimate for bigger buyers, but it is a real annual cost that "
             "was not in your quote. Ask for the limits and the deadline."),
        fix=("Contractor maintains professional liability insurance with limits "
             "of at least the fees paid under this Agreement; Client "
             "reimburses the premium where limits above that are requested."),
        ask="What limits do you actually need? I'll add the premium to the quote if it exceeds my standard cover.",
    ),

    # ----------------------------------------------------------- control ---- #
    Rule(
        rid="exclusivity-noncompete",
        title="You may not work for anyone else",
        category="control", severity=3,
        any_of=[r"shall not (?:engage in|perform|provide|offer|accept|work)",
                r"exclusively for", r"no (?:other )?(?:clients?|engagements?) during",
                r"non-?compet"],
        all_of=[[r"competitor", r"other client", r"any (?:other|third[- ]party) (?:person|entity|client)",
                r"same (?:industry|sector|market)", r"exclusiv"]],
        why=("An exclusivity clause turns a project fee into a salary with no "
             "employment rights, no benefits and no job security. In several "
             "countries an unpaid non-compete of this kind is also unenforceable "
             "-- which does not stop it being used as a threat."),
        fix=("Contractor is not exclusive and may provide services to other "
             "clients, provided Contractor does not work for any person "
             "identified to Contractor in writing as a direct competitor of "
             "Client for this project, for the duration of the engagement only."),
        ask="I need to keep taking other work. Can we limit this to named direct competitors, during the project only?",
    ),
    Rule(
        rid="post-term-restraint",
        title="Restraint continues after the contract ends",
        category="control", severity=3,
        any_of=[r"after (?:the )?(?:expiry|termination|end) of (?:the )?(?:term|agreement)",
                r"after (?:its|the|such) termination", r"following (?:the )?termination",
                r"post[- ]termination", r"after (?:the )?(?:date of )?(?:completion|conclusion)",
                r"for \d+\s*(?:months?|years?) (?:after|following|from)",
                r"(?:months?|years?) .{0,20}after .{0,20}(?:termination|expiry|end)"],
        all_of=[[r"shall not", r"may not", r"refrain from", r"non-?compet"],
                [r"competitor", r"client", r"similar (?:services|work)", r"industry|sector|market"]],
        why=("Post-term restraints on an individual rarely survive scrutiny and "
             "almost never get paid for, yet they freeze your pipeline for the "
             "stated period exactly when you most need to refill it."),
        fix="Any post-term restriction is limited to 6 months, to named competitors, and is conditioned on separate agreed consideration.",
        ask="If it runs after the project, there needs to be consideration for it. Otherwise can we cut it to during the project?",
    ),
    Rule(
        rid="employee-style-control",
        title="They control how and when you work",
        category="control", severity=2,
        any_of=[r"(?:shall|must) (?:be available|work|attend|sit) .{0,40}(?:hours|days|office|9|9:00|office days)",
                r"dedicate.{0,30}(?:time|hours|bandwidth)", r"follow(?:s|ing)?.{0,40}(?:internal|company) polic",
                r"report (?:to|in) (?:daily|weekly) .{0,30}manager",
                r"supervis.{0,40}(?:direction|control) of (?:client|its)"],
        why=("This is how contractor-status reviews and IR35-style tests read "
             "the paperwork: control over hours, methods and supervision points "
             "to employment. The client gets the flexibility without the payroll "
             "taxes, and you can be reclassified after the fact."),
        fix=("Contractor determines the method, hours and location of work and "
             "is not subject to Client's internal policies or supervision "
             "beyond reasonable coordination of milestones."),
        ask="We're an outside supplier, so can we drop the hours/policy language and just hold a weekly milestone check-in?",
    ),
    Rule(
        rid="unilateral-scope",
        title="Client may change scope at its discretion",
        category="control", severity=2,
        any_of=[r"(?:client|company) may (?:modify|change|amend|vary|extend|adjust)",
                r"additional (?:work|tasks|requests) .{0,40}(?:reasonable|as required|as needed)"],
        all_of=[[r"scope", r"deliverable", r"services", r"requirements", r"at any time", r"sole discretion"]],
        none_of=[r"(?:change request|change order).{0,60}(?:fee|rate|pricing|adjust)",
                 r"affects? (?:the )?(?:fee|timeline) .{0,30}(?:amend|adjust|agree)"],
        why=("Combined with a fixed fee, 'we may add reasonable requests' is an "
             "open invitation to scope creep. Requests need to move the price or "
             "the date, in writing."),
        fix=("Either party may raise a written change request. Each must state "
             "the effect on fee and schedule and takes effect only on written "
             "acceptance; work ordered before acceptance is charged at the "
             "hourly rate in Schedule B."),
        ask="Change requests need to carry a fee and a date impact, otherwise a fixed price can't work. Agreed?",
    ),
    Rule(
        rid="unlimited-revisions",
        title="Unlimited revisions",
        category="control", severity=2,
        any_of=[r"unlimited (?:revisions?|iterations?|changes|rounds)",
                r"(?:revisions?|changes) .{0,30}until .{0,30}(?:client|approval|satisfaction)",
                r"as many (?:revisions?|rounds) as", r"indefinite .{0,20}(?:revisions?|rounds)",
                r"such further (?:changes?|revisions?|work|requests?|amendments?)",
                r"(?:further|additional) (?:changes?|revisions?|work) (?:as|on) .{0,40}request"],
        all_of=[[r"until (?:the )?client (?:is |be )?satisf", r"until (?:final |client'?s )?approval",
                 r"reasonably request", r"from time to time", r"as (?:the )?client (?:may|requires|directs)",
                 r"satisf(?:ied|action)"]],
        why=("The clause that turns a fixed-fee project into an hourly loss. "
             "Pricing assumes a bounded loop; unlimited rounds means the "
             "effective rate falls every week until the client is bored."),
        fix=("Fee includes 2 rounds of consolidated revisions per Deliverable. "
             "Further rounds are billed at the hourly rate in Schedule B, or as "
             "a fixed revision package agreed in writing."),
        ask="How many revision rounds does the fee cover? I've built it for two -- beyond that I bill.",
    ),
    Rule(
        rid="sole-discretion",
        title="Discretionary decisions reserved to Client",
        category="terms", severity=1,
        any_of=[r"sole (?:and (?:absolute |full )?)?discretion", r"absolute discretion",
                r"(?:may|will be) withheld .{0,25}not unreasonably"],
        why=("Not fatal on its own, but every 'sole discretion' is a decision "
             "you cannot plan around -- approvals, expenses, extensions. 'Not "
             "unreasonably' costs them nothing and gives you recourse."),
        fix="Replace 'at its sole discretion' with 'acting reasonably and in good time, in writing'.",
        ask="Any chance of 'acting reasonably' instead of 'sole discretion'? Same outcome, less ambiguity.",
    ),
    Rule(
        rid="revocable-license",
        title="Your licence to the work can be revoked",
        category="ip", severity=2,
        any_of=[r"(?:licence|license)s? .{0,60}\brevocable\b", r"\brevocable .{0,30}(?:licence|license)",
                r"(?:licence|license).{0,40}\b(?:terminable|withdrawable)\b",
                r"may (?:revoke|withdraw) any (?:licence|license)",
                r"(?:licence|license) .{0,30}may be (?:revoked|withdrawn)"],
        none_of=[r"irrevocable", r"not (?:be )?revoked", r"perpetual"],
        why=("If the transfer failed but the client granted a licence instead, "
             "a revocable licence can be pulled after launch -- a hostage "
             "situation on work you already delivered and invoiced."),
        fix="Client is granted a perpetual, irrevocable, non-exclusive licence for the agreed purpose, on payment in full.",
        ask="Make the licence perpetual and irrevocable once paid, otherwise the handover isn't real.",
    ),

    # -------------------------------------------------------------- exit ---- #
    Rule(
        rid="convenience-termination",
        title="They can end it any time with little notice",
        category="exit", severity=2,
        any_of=[r"(?:terminate|cancel) .{0,40}(?:at any time|for convenience|without cause|immediately)",
                r"(?:may|shall) terminate (?:this agreement|the order)? ?.{0,25}(?:at any time|without reason|immediately)",
                r"terminat\w+ at (?:client|company)'?s sole (?:discretion|option)"],
        all_of=[[r"client", r"company", r"either party"]],
        none_of=[r"either party may terminate", r"pay\w* .{0,40}(?:work performed|fees accrued|work done|work completed|approved work)"],
        why=("Termination for convenience is normal; without notice and a "
             "kill fee it means the capacity you reserved for them is wasted "
             "and unpaid. The gap it blows in your diary is the real cost."),
        fix=("Client may terminate for convenience on 14 days' written notice "
             "and pays for work performed to that date plus a kill fee of 25% "
             "of the fees for the unperformed balance."),
        ask="If you can pull the plug, I need notice plus a kill fee -- otherwise I'm holding dates I can't sell.",
    ),
    Rule(
        rid="no-pay-for-wip",
        title="No payment for work in progress on termination",
        category="exit", severity=3,
        any_of=[r"no (?:further|additional|any) (?:payment|compensation|liability)",
                r"(?:shall|will) not (?:be liable|pay) .{0,40}(?:work in progress|part[- ]performed|incomplete)",
                r"termination.{0,60}(?:without|free of) (?:any )?(?:further )?(?:liability|payment)"],
        all_of=[[r"terminat", r"cancell", r"withdraw", r"discontinu"]],
        why=("The worst pairing with an IP-assignment clause: they keep the "
             "drafts, pay nothing, and your half-finished work is already "
             "legally theirs."),
        fix="On any termination Client pays for all work performed to the termination date, and retains Deliverables only on payment.",
        ask="On termination you'd pay for work done to date. Can we add that sentence?",
    ),
    Rule(
        rid="auto-renew",
        title="Evergreen renewal with a narrow opt-out",
        category="exit", severity=2,
        any_of=[r"automatically renew", r"evergreen", r"shall renew .{0,40}unless",
                r"continue[sd]? (?:in )?force .{0,40}unless (?:terminated|notice)"],
        why=("A renewal window you can miss by a week converts a one-off "
             "project into a year of committed capacity at last year's rate, "
             "and locks the exit behind the same notice period."),
        fix=("Renewal requires both parties' written agreement. Client may "
             "cancel any time on 30 days' notice, and rates are reviewed at "
             "each renewal."),
        ask="Can renewal be opt-in rather than opt-out? If it auto-renews, I need the current rate reviewed first.",
    ),
    Rule(
        rid="short-notice",
        title="Short cancellation notice window",
        category="exit", severity=1,
        any_of=[r"\d{1,3}\s*(?:business )?days'? .{0,25}(?:prior )?(?:written )?notice",
                r"notice period of \d+"],
        all_of=[[r"terminat", r"cancel", r"renew", r"expir", r"withdraw", r"non[- ]?renew"]],
        none_of=[r"suspend", r"payment of", r"deliver\w* the notice to client"],
        where=lambda flow: 0 < longest_notice(flow) < 14,
        why=("Two weeks' notice on a reserved month is a small version of the "
             "same problem as no notice. Thirty days is the freelance norm for "
             "retainers."),
        fix="Either party may terminate on 30 days' written notice; Client pays for work performed and non-cancellable commitments.",
        ask="For a retainer I need 30 days either way so I can refill the dates.",
    ),
    Rule(
        rid="assignment-their-side",
        title="They can assign you to another business",
        category="terms", severity=1,
        any_of=[r"(?:client|company) may (?:freely )?assign"],
        all_of=[[r"this agreement", r"rights", r"obligations"]],
        none_of=[r"contractor may not assign"],
        why=("Your NDA and your working relationship can end up transferred to "
             "a company you never agreed to work with -- possibly one you would "
             "have declined."),
        fix="Neither party may assign this Agreement without the other's written consent, not to be unreasonably withheld.",
        ask="Make assignment mutual and consent-based, not one-way.",
    ),
    Rule(
        rid="far-venue-arbitration",
        title="Disputes must be fought on their turf",
        category="terms", severity=2,
        any_of=[r"exclusive (?:jurisdiction|venue)", r"courts? of .{0,40}(?:shall have|exclusive)",
                r"mandatory arbitration", r"binding arbitration",
                r"resolved through arbitration", r"arbitration in [a-z]",
                r"venue of arbitration", r"waiv\w+ .{0,30}class action"],
        why=("A $4,000 invoice is not worth flying to another country to "
             "enforce, which both sides know. Small-claims in your own "
             "jurisdiction is the practical remedy for individuals."),
        fix=("Disputes are first escalated to senior representatives for 14 "
             "days, then decided by the courts of [Contractor's jurisdiction] "
             "or by small-claims procedure, and either party may still seek "
             "interim relief where the breach occurs."),
        ask="Can we make venue neutral, or at least keep small invoices in small claims where either of us is?",
    ),
    Rule(
        rid="perpetual-secrecy",
        title="Confidentiality never ends",
        category="terms", severity=1,
        any_of=[r"(?:confidentiality|obligations).{0,60}(?:perpetual|in perpetuity|indefinitely|survives? indefinitely)",
                r"survive(?:s|d)? .{0,30}(?:termination|expiry) .{0,30}(?:indefinitely|perpetually|without limit)"],
        none_of=[r"\d+ years? (?:after|following)"],
        why=("Perpetual secrecy over-burdens a normal engagement, and after a "
             "few years almost everything it covers is public anyway. Five "
             "years, or three for non-trade-secret information, is the norm."),
        fix="Confidentiality obligations continue for 5 years after termination (indefinitely only for genuine trade secrets).",
        ask="Can we put a 5-year tail on confidentiality? Perpetual is hard to honour in practice.",
    ),
    Rule(
        rid="overbroad-confidentiality",
        title="Secret includes your own skill",
        category="terms", severity=2,
        any_of=[r"all information.{0,80}(?:including|without limitation)",
                r"confidential .{0,50}(?:general (?:skills|knowledge)|know[- ]how|techniques? learned)",
                r"(?:any|all) (?:information|material).{0,40}(?:learned|observed|obtained|disclosed)"],
        none_of=[r"(?:marked|designated) (?:as )?confidential", r"would (?:reasonably )?be understood to be confidential"],
        why=("A definition that sweeps in what you learned and observed can be "
             "read against you reusing your own craft on someone else's "
             "project. Confidentiality needs to mark itself, not be guessed."),
        fix=("Confidential Information means information disclosed in writing "
             "and marked confidential, or information a reasonable person "
             "would understand to be confidential, and excludes general "
             "skills, knowledge and experience retained by Contractor."),
        ask="Please limit confidential info to things marked confidential -- my general skills have to stay usable.",
    ),

    # ------------------------------------------------- whole-document rules - #
    Rule(
        rid="no-liability-cap-anywhere",
        title="There is no liability cap at all",
        category="risk", severity=2, doc_scope=True,
        any_of=[r"shall not exceed|liability.{0,60}capped|aggregate liability|not (?:be )?liable for .{0,30}exceed"],
        why=("Nothing in the agreement limits what either side can be sued for. "
             "Caps are usually mutual and cost the client nothing to give; "
             "their absence is what makes small projects feel like large risks."),
        fix="Mutual cap: each party's total liability is limited to fees paid in the preceding 12 months; indirect and consequential loss excluded.",
        ask="There's no cap anywhere. Can we add a mutual one at fees paid?",
    ),
    Rule(
        rid="no-deposit-required",
        title="No deposit or upfront payment",
        category="money", severity=1, doc_scope=True,
        any_of=[r"deposit|upfront|in advance|on commencement|50% (?:of|upon)|mobilis"],
        why=("Without a deposit you are financing the first weeks of the job "
             "and have no signal that the buyer is serious. A 30-50% deposit "
             "is standard and reduces ghosting to near zero."),
        fix="A deposit of 40% of the fixed fee is due on signature and before Contractor starts.",
        ask="Can we put a 40% deposit on signature? It's how I hold the dates.",
    ),
    Rule(
        rid="no-late-payment-interest",
        title="No interest on late invoices",
        category="money", severity=1, doc_scope=True,
        any_of=[r"interest .{0,40}(?:late|overdue|unpaid|delay)|late .{0,30}(?:interest|charge|fee)",
                r"statutory .{0,30}interest", r"accru\w* .{0,25}interest",
                r"interest (?:of |at )?[\d.]{1,4}\s*%", r"interest (?:shall )?apply"],
        why=("An invoice that is late with no consequence is a free loan from "
             "you to them. Interest is also the cheapest way to change a "
             "client's payment behaviour without a confrontation."),
        fix="Overdue invoices accrue interest at 1.5% per month (or the maximum permitted by law), plus suspension of work after 21 days unpaid.",
        ask="Can we add late-payment interest? In practice nobody pays if there's no cost to waiting.",
    ),
    Rule(
        rid="no-acceptance-criteria",
        title="No written acceptance criteria",
        category="money", severity=2, doc_scope=True,
        any_of=[r"acceptance criteria|specification in schedule|deliverables in schedule|statement of work in schedule|scope .{0,40}(?:schedule|annex|appendix)"],
        why=("Without a written definition of done, acceptance becomes a "
             "preference -- and preference is the argument you lose at the end "
             "of a project, after the money has already gone out."),
        fix="Schedule A lists each Deliverable with objective acceptance criteria; Deliverables not rejected in writing within 10 business days are deemed accepted.",
        ask="We need a Schedule A with what 'done' means for each deliverable, otherwise 'accepted' is undefined.",
    ),
    Rule(
        rid="no-preexisting-tools-carve-out",
        title="No carve-out for your existing tools",
        category="ip", severity=2, doc_scope=True,
        any_of=[r"pre-?existing|background ip|prior (?:works?|materials?)|contractor'?s (?:tools|templates|libraries)"],
        why=("Blanket assignment of 'all work product' can be read to sweep in "
             "the component library, boilerplate or method you brought with you "
             "and use on every job -- the base of the business, transferred "
             "away for the price of one project."),
        fix=("Contractor retains all right, title and interest in its "
             "pre-existing materials and tooling ('Background IP'), and grants "
             "Client a perpetual, non-exclusive licence to use Background IP "
             "as embedded in the Deliverables."),
        ask="I reuse a component library across clients. Can we carve that out and license it to you instead of assigning it?",
    ),
    Rule(
        rid="no-suspension-right",
        title="You cannot stop work when unpaid",
        category="money", severity=1, doc_scope=True,
        any_of=[r"suspend|stop work|pause (?:the )?(?:work|services)|cease .{0,30}(?:work|services)"],
        all_of=[[r"unpaid", r"overdue", r"not paid", r"fails to pay"]],
        why=("Your only practical leverage on a late invoice is to stop. "
             "Contracts that forbid suspension while keeping 'time is of the "
             "essence' leave you performing at your own cost with no remedy."),
        fix=("Contractor may suspend work on 7 days' written notice if an "
             "invoice is more than 14 days overdue; timelines extend by the "
             "period of suspension and resumption follows payment."),
        ask="If an invoice is 14 days late I need the right to pause, with dates extended by the pause.",
    ),
]

# Rules that fire when a whole-document concept is missing: any_of must NOT
# match anywhere. ``doc_scope`` rules therefore invert their own sense.
ABSENCE_RULES = [r for r in RULES if r.doc_scope]
CLAUSE_RULES = [r for r in RULES if not r.doc_scope]

SEVERITY_LABEL = {3: "stop", 2: "fix", 1: "ask", 0: "note"}
SEVERITY_LONG = {3: "do not sign like this", 2: "fix before signing",
                 1: "worth asking", 0: "note only"}
