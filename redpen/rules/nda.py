"""Rules for NDAs and confidentiality agreements.

The pattern with NDAs is that the damage is rarely in the obvious clause. Nobody
signs a document that says "you may never work again". It is the term that
survives "until such time as all Confidential Information becomes publicly
known" -- which is to say never -- the indemnity that appears inside a
confidentiality agreement where nobody expects to find one, and the publicity
clause that quietly forbids you from mentioning that you did the work.

These also apply to a document type where the freelance library is close to
useless: there is no fee, no invoice and no deliverable in an NDA, so the
payment rules would either stay silent or report nonsense.
"""

from __future__ import annotations

from .catalog import Rule

NDA_RULES: list[Rule] = [

    Rule(
        rid="nda-perpetual-by-definition",
        title="Confidentiality effectively never ends",
        category="terms", severity=2, applies_to="nda",
        any_of=[r"survive .{0,40}until such time as all confidential information",
                r"until .{0,40}(?:becomes? publicly known|generally available through no action)",
                r"obligations? .{0,40}(?:survive|continue)[^.]{0,40}(?:indefinitely|perpetually|without limitation)",
                r"in perpetuity"],
        none_of=[r"\d+ years? (?:after|following|from)", r"for a period of \d+ years"],
        why=("Drafted this way the obligation ends only when every piece of "
             "confidential information has become public -- which never happens, "
             "because the bar is *all* of it. You are agreeing to permanent "
             "confidentiality with a poetic wrapper, and to being able to prove it "
             "years later."),
        fix=("Confidentiality obligations continue for 5 years after the last "
             "disclosure, and indefinitely only for information that is a trade "
             "secret under applicable law."),
        ask=("Can we put a 5-year tail on it, with perpetual cover only for genuine "
             "trade secrets? 'Until everything is public' is effectively forever."),
    ),
    Rule(
        rid="nda-no-term-end",
        title="No end date for your obligations",
        category="terms", severity=2, applies_to="nda", doc_scope=True,
        any_of=[r"(?:term|duration|period) of this agreement", r"\d+ years?",
                r"expire[sd]? on", r"shall remain in force for", r"shall survive",
                r"obligations? .{0,30}(?:continue|survive)"],
        why=("An NDA with no term is open-ended in both directions: you cannot say "
             "when you will be free to work in an adjacent space, and there is no "
             "date after which a former colleague's casual remark stops being a "
             "potential claim."),
        fix=("This Agreement is in force for the term of the engagement and 3 years "
             "afterwards, except for trade secrets."),
        ask=("Is there an end date on the obligations? I'd like 3 years after we "
             "stop working together."),
    ),
    Rule(
        rid="nda-indemnity-hidden",
        title="An indemnity is buried in the confidentiality agreement",
        category="risk", severity=3, applies_to="nda",
        any_of=[r"keep indemnified against any (?:losses|damages)",
                r"indemnify .{0,50}(?:losses|damages)[^.]{0,60}attorneys",
                r"indemnif\w+ .{0,60}(?:reasonable )?(?:attorney|lawyer)s?[' ]?s? ?fees"],
        none_of=[r"each party indemnifies the other", r"mutual.{0,30}indemnif",
                 r"capped at"],
        why=("NDAs are usually read as low-risk paperwork, which is exactly why an "
             "indemnity is effective in one. This obliges you to pay their losses "
             "and legal fees on a breach allegation, with no cap and no "
             "requirement that the loss be reasonable or foreseeable."),
        fix=("Either party is liable for direct losses caused by its own breach; "
             "no indemnity for the other party's legal costs, and each party's "
             "liability is capped at the fees payable under the main agreement or "
             "INR 1,00,000, whichever is lower."),
        ask=("Can we drop the indemnity and keep it to direct loss from a breach, "
             "both ways? An open-ended costs clause in an NDA isn't something I can "
             "price."),
    ),
    Rule(
        rid="nda-one-way-injunctive",
        title="Injunctive relief without bond, for them only",
        category="risk", severity=1, applies_to="nda",
        any_of=[r"without a requirement to post bond", r"waive .{0,40}(?:requirement of|the posting of) (?:a )?bond",
                r"irreparable harm .{0,60}(?:shall|is) (?:be )?presumed",
                r"entitled to seek (?:preliminary and )?injunctive relief"],
        none_of=[r"each party (?:may|is entitled to) seek", r"either party .{0,40}injunctive"],
        why=("Injunctive relief is normal and often fair. One-way, no-bond relief "
             "is not: they can shut down your work immediately on an allegation, "
             "without posting security against the damage if they turn out to be "
             "wrong."),
        fix=("Either party may seek injunctive relief for breach of confidentiality "
             "or trade-secret obligations."),
        ask=("Make the injunction right mutual -- I'm not asking to remove it."),
    ),
    Rule(
        rid="nda-oral-catch-all",
        title="Confidential information includes anything said out loud",
        category="terms", severity=2, applies_to="nda",
        any_of=[r"whether electronic, written or oral", r"(?:information|data)[^.]{0,40}\boral\b",
                r"relating to .{0,80}(?:business|operations|financials|services|facilities)",
                r"(?:would reasonably be understood|deemed to be confidential)"],
        none_of=[r"(?:marked|designated) (?:as )?confidential",
                 r"confirmed in writing within \d+ days",
                 r"excludes? .{0,60}(?:general skills|knowledge|experience)"],
        why=("Oral, unmarked information 'relating to business, operations, "
             "financials, services and facilities' is not a boundary you can "
             "operate inside -- you will not remember which overheard sentence was "
             "contractually secret. The standard fix costs the discloser nothing: "
             "mark it, or confirm it in writing within a few days."),
        fix=("Confidential Information means information marked confidential, or "
             "disclosed orally and confirmed in writing within 15 days, and "
             "excludes general skills, knowledge and experience."),
        ask=("For anything said verbally, can we require a written confirmation "
             "within 15 days? Otherwise I can't tell what's covered."),
    ),
    Rule(
        rid="nda-no-portfolio-reference",
        title="You may not say you worked together",
        category="ip", severity=2, applies_to="nda",
        any_of=[r"shall not promote or otherwise disclose the existence of the relationship",
                r"not (?:disclose|announce|reference) .{0,40}(?:existence of the|our) relationship",
                r"for purposes of soliciting or procuring (?:sales|clients|business)",
                r"no (?:press release|publicity|announcement) .{0,60}(?:name|logo|client)"],
        none_of=[r"with (?:prior |the other party'?s)?(?:written )?consent",
                 r"(?:portfolio|case stud|credentials|reference)"],
        why=("This is a confidentiality clause doing a marketing job. For an "
             "independent, being unable to name a client or even confirm that a "
             "relationship exists costs you the reference -- and it usually "
             "survives long after the secrets have gone stale."),
        fix=("Neither party discloses the other's confidential information; either "
             "may state that a working relationship existed and use the other's "
             "name in lists of clients, on consent or 6 months after the work ends."),
        ask=("Confidentiality, absolutely. Can I still list you as a client and "
             "say we worked together once the project is done?"),
    ),
    Rule(
        rid="nda-one-way-assignment",
        title="Only you are barred from assigning",
        category="terms", severity=1, applies_to="nda",
        any_of=[r"obligations of the (?:supplier|recipient|receiving party|you)[^.]{0,60}(?:shall not|not) be assignable",
                r"neither[^.]{0,60}obligations of the (?:supplier|recipient|receiving party)[^.]{0,40}assignable",
                r"(?:supplier|recipient)[^.]{0,60}without the prior written consent of"],
        none_of=[r"neither party may assign", r"either party .{0,30}assign"],
        why=("Asymmetric assignment lets them transfer the agreement to an entity "
             "you never dealt with -- an acquirer, a holding company, a subsidiary "
             "in another jurisdiction -- while you stay locked to them."),
        fix=("Neither party may assign this Agreement without the other's written "
             "consent, except to a successor of the whole business on notice."),
        ask=("Make assignment mutual."),
    ),
    Rule(
        rid="nda-return-destroy-no-carveout",
        title="Return or destroy everything, with no archive carve-out",
        category="terms", severity=1, applies_to="nda",
        any_of=[r"(?:return to or destroy|destroy or return)[^.]{0,60}all confidential information",
                r"at the option of .{0,30}(?:disclosing party|the company)",
                r"promptly (?:return|destroy)[^.]{0,60}(?:backup|electronic|copies)"],
        none_of=[r"except .{0,60}(?:retained pursuant to (?:law|retention policy)|one archival copy|automated backup)",
                 r"no obligation to delete .{0,40}backup"],
        why=("A pure destroy-everything obligation collides with ordinary reality: "
             "email backups, accounting records you are required to keep, and your "
             "own proof of what you were told. The standard carve-out protects "
             "their confidentiality and your ability to comply honestly."),
        fix=("Return or destroy on request, except one archival copy retained under "
             "the same confidentiality obligations where required by law or "
             "automated backup systems."),
        ask=("Can we add the usual carve-out for legally required retention and "
             "automated backups?"),
    ),
    Rule(
        rid="nda-staff-flowdown-liability",
        title="You are answerable for people you do not control",
        category="risk", severity=1, applies_to="nda",
        any_of=[r"(?:staff|employees|personnel|subcontractors)[^.]{0,80}(?:comply with|bound by)[^.]{0,60}confidential",
                r"(?:liable|responsible) for .{0,40}(?:acts|breaches|omissions) .{0,30}(?:staff|its employees|representatives)"],
        none_of=[r"(?:reasonable efforts|procure that)[^.]{0,40}(?:bound|comply)",
                 r"each party is responsible for its own"],
        why=("Flowing obligations down to your team is normal. Making you strictly "
             "liable for their conduct, with no cap, converts someone else's "
             "mistake into your uncapped exposure."),
        fix=("Each party procures that its personnel are bound by equivalent "
             "obligations and is responsible for its own personnel's breach."),
        ask=("I'll bind my team to the same terms -- can liability stay with "
             "whoever actually breached?"),
    ),
    Rule(
        rid="nda-no-general-skills-carveout",
        title="Nothing reserves your general skills",
        category="control", severity=2, applies_to="nda", doc_scope=True,
        any_of=[r"general (?:skills|knowledge|expertise|experience)",
                r"memory ?(?:residual|information)?", r"residual information",
                r"(?:shall|does) not (?:limit|restrict) .{0,50}(?:use of .{0,30}(?:skills|knowledge)|employee'?s general)"],
        why=("Without a general-skills carve-out, the line between 'I learned a "
             "technique at that company' and 'I disclosed their confidential "
             "information' is undefined -- and it is the line your next job "
             "depends on. A carve-out for unaided memory is standard and does not "
             "weaken real secrecy."),
        fix=("Nothing in this Agreement prevents use of general skills, knowledge "
             "and experience retained in unaided memory, provided no Confidential "
             "Information is deliberately recalled or disclosed."),
        ask=("Can we add the unaided-memory carve-out? It doesn't touch anything "
             "genuinely confidential."),
    ),
]
