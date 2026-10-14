"""Rules for offer letters, internships and employment terms.

Every pattern here was taken from the phrasing in real Indian offer letters and
internship agreements, not invented. That matters: the freelance library asks
about deposits, invoices and acceptance criteria, and an internship letter has
none of those. Running the services rules over an offer letter produced four
"missing term" findings that were pure noise sitting next to one real problem --
which is exactly how a tool like this loses a user's trust on the first run.

The distinctive harms in employment documents are also different in kind from
B2B contracts: original certificates held hostage, a notice period that only
binds one side, unpaid trial days, and a conversion promise that depends on
vacancies.
"""

from __future__ import annotations

from .catalog import Rule

EMPLOYMENT_RULES: list[Rule] = [

    Rule(
        rid="unpaid-trial-period",
        title="You work some days for nothing",
        category="money", severity=3, applies_to="employment",
        any_of=[r"unpaid (?:training|probation|trial|internship) period",
                r"first \d+ days .{0,40}unpaid", r"period .{0,30}(?:shall|will) be unpaid",
                r"no (?:stipend|remuneration|payment) .{0,40}(?:training|probation|first)"],
        why=("Unpaid trial days are the one term that turns 'we will see how you "
             "do' into you funding the employer's evaluation. If the role is "
             "productive work, the time is worked for free and you have already "
             "committed before earning anything."),
        fix=("Stipend is payable from day one, including the training period. If "
             "a probation assessment period is required, it is paid at the same "
             "rate and counted towards tenure."),
        ask=("Can the training period be paid? I'm happy to be assessed during it, "
             "but I can't work ten days without stipend."),
    ),
    Rule(
        rid="original-documents-held",
        title="Your original certificates are held by the employer",
        category="risk", severity=3, applies_to="employment",
        any_of=[r"original (?:documents?|marksheets?|certificates?)[^.]{0,90}(?:returned|retained|submitted|kept|provided)",
                r"(?:submit|provide|deposit)[^.]{0,50}original (?:marksheets?|certificates?|documents?)",
                r"replacement document .{0,60}(?:approved|hr)",
                r"originals will be returned .{0,60}(?:completion|end of)"],
        none_of=[r"will not be (?:retained|held|kept|collected)",
                 r"(?:are|shall) not (?:be )?(?:retained|held|collected)",
                 r"never (?:be )?(?:retained|held|collected)",
                 r"no original (?:documents|certificates|marksheets)"],
        why=("Holding your original marksheet or degree is the single most "
             "effective way to make sure you cannot leave. It is not security for "
             "the employer -- it is leverage over you, and asking for a "
             "'replacement document approved by HR' to get your own certificate "
             "back makes the dependency explicit. Several Indian states treat this "
             "as unlawful, and no legitimate employer needs your originals."),
        fix=("Employee provides self-attested copies only. Originals are neither "
             "collected nor retained, and verification is by sight of the original "
             "and return on the same day."),
        ask=("I can bring originals for verification and leave certified copies, "
             "but I can't hand over the originals. Is that workable?"),
    ),
    Rule(
        rid="asymmetric-notice",
        title="Notice binds you but not them",
        category="exit", severity=3, applies_to="employment",
        any_of=[r"(?:you|employee|intern|candidate) (?:shall|has to|have to|will) (?:serve|give|provide|inform)[^.]{0,40}(?:notice|one month|1 month|30 days|prior)",
                r"notice period of (?:one|1|\d+) month[^.]{0,60}(?:pay|compensation|recovery)",
                r"(?:company|employer|organization|organization)?[^.]{0,30}(?:may|has the right to) terminate[^.]{0,50}(?:at any time|any time|forthwith|without (?:assigning|any) reason|immediately)"],
        all_of=[[r"terminate|discontinue|notice|exit"]],
        none_of=[r"(?:either|both) (?:party|parties|side) may terminate[^.]{0,40}(?:same|equal|like) notice",
                 r"employer shall (?:give|serve) .{0,20}(?:same|equal) notice"],
        why=("Read the two halves together: you must give a month or pay for it, "
             "and they can end it at any time. The asymmetry is the whole point -- "
             "you carry the cost of leaving and none of the certainty of staying."),
        fix=("Either party may terminate on 30 days' written notice or pay in lieu. "
             "No recovery is made from the intern for notice, and termination by "
             "the Company requires the same notice save for proven misconduct."),
        ask=("Notice needs to run both ways on the same terms. Can we make it "
             "30 days either side?"),
    ),
    Rule(
        rid="subjective-performance-termination",
        title="Employment can end for 'not satisfactory' performance",
        category="exit", severity=2, applies_to="employment",
        any_of=[r"if your performance is not satisfactory",
                r"(?:may|can) terminate .{0,50}(?:if|where).{0,40}(?:performance|work) .{0,30}(?:not satisfactory|unsatisfactory)",
                r"unsatisfactory performance .{0,50}terminat",
                r"not (?:up to the mark|meeting expectations)[^.]{0,60}terminat"],
        none_of=[r"(?:written|documented) (?:warning|feedback|criteria)[^.]{0,80}(?:opportunity|cure|remedy)",
                 r"defined (?:kpi|target|criteria)"],
        why=("'Satisfactory' with no written criteria and no improvement step is "
             "not a performance clause, it is a discretionary exit clause with a "
             " euphemism on it. You cannot manage to a standard you were never given."),
        fix=("Termination for performance requires written criteria at the start, "
             "one written review with specific gaps, and a 30-day improvement "
             "window before any termination."),
        ask=("What are the written performance criteria, and can we add a review "
             "plus improvement window before termination?"),
    ),
    Rule(
        rid="business-exigencies-termination",
        title="They can end it immediately for 'business exigencies'",
        category="exit", severity=2, applies_to="employment",
        any_of=[r"forthwith[^.]{0,80}business exigenc", r"business exigenc",
                r"immediate termination .{0,50}(?:without|no) (?:notice|compensation)",
                r"terminate .{0,30}without assigning any reason"],
        why=("Business exigency is undefined and unfalsifiable, so it is available "
             "for any reason including the ordinary one of not needing you this "
             "month. Combined with no notice pay, the risk of a mid-month stop sits "
             "entirely with you."),
        fix=("Termination on short notice for genuine business reasons requires "
             "payment in lieu of notice and stipend for work already performed."),
        ask=("If you ever need to cut it short, can we keep notice pay in lieu and "
             "settle what I've worked to that date?"),
    ),
    Rule(
        rid="discretionary-conversion",
        title="A job promise that depends on vacancies",
        category="money", severity=1, applies_to="employment",
        any_of=[r"may offer you? a full[- ]time position[^.]{0,60}(?:vacanc|performance|at (?:the )?(?:company'?s|our) discretion)",
                r"based on vacancies",
                r"(?:pre[-\s]?placement offer|conversion)[^.]{0,120}(?:depending on|subject to|based on|may)",
                r"may or may not entitle you to an employment offer",
                r"package shall be depending on", r"eligible for a pre[-\s]?placement"],
        why=("This is the part of an internship that people actually make life "
             "decisions on, and it is written so that it binds nobody. 'May, based "
             "on vacancies, depending on performance' is an option, not an offer -- "
             "worth knowing before you turn something else down."),
        fix=("Any conversion is assessed against written criteria and communicated "
             "in writing at least 30 days before the internship ends; the Company "
             "gives a yes or no rather than leaving it open."),
        ask=("I'm not asking for a guarantee, but can I get a written yes or no "
             "30 days before the end, so I can plan?"),
    ),
    Rule(
        rid="final-settlement-delay",
        title="Final payment delayed and conditioned on undefined terms",
        category="money", severity=2, applies_to="employment",
        any_of=[r"full and final[^.]{0,90}(?:after|within) (?:\d+|\w+) days",
                r"(?:after|within) (?:45|60|90) days[^.]{0,60}(?:exit formalities|completion|resigning)",
                r"t&c applicable as per (?:the )?discussion", r"subject to (?:the )?applicable t&c"],
        none_of=[r"within (?:7|10|14|15|21|30) days"],
        why=("Forty-five days is a long time to be owed money, and 'T&C as per the "
             "discussion during exit' means the conditions are decided after you "
             "have already left and have no leverage. Settlement timing needs a "
             "number and a definition, not a reference to a conversation."),
        fix=("Full and final settlement is paid within 30 days of the last working "
             "day, and any deduction is itemised in writing with the basis stated "
             "before it is applied."),
        ask=("Can we fix F&F at 30 days and list any deduction in writing with its "
             "basis before it's applied?"),
    ),
    Rule(
        rid="benefits-excluded",
        title="No benefits, and no route to them",
        category="terms", severity=1, applies_to="employment",
        any_of=[r"not (?:be )?eligible for any (?:company[- ]sponsored )?benefits",
                r"will not receive any of the employee benefits",
                r"not entitled to .{0,40}(?:insurance|pf|esi|leave|benefits)"],
        why=("Normal for a genuine internship and worth knowing rather than "
             "arguing about: no ESI or insurance means an illness or an accident "
             "commuting to this role is entirely on you for the whole term."),
        fix=("Company provides accident and medical cover for the duration of the "
             "internship, or confirms in writing that none is provided so the "
             "intern can arrange cover and be reimbursed."),
        ask=("Is there any accident or medical cover for the internship? If not "
             "I'll arrange my own and add it to the cost."),
    ),
    Rule(
        rid="open-ended-duty-scope",
        title="Your duties include anything they later need",
        category="control", severity=2, applies_to="employment",
        any_of=[r"including[,]? but not limited to", r"any future requirements",
                r"other tasks as (?:assigned|directed|required)",
                r"(?:duties|responsibilities) .{0,50}(?:as assigned|from time to time|as may be determined)"],
        why=("A Front-end Intern who owes work on 'AI/ML, mobile, DevOps, system "
             "and network administration' is not a front-end intern. It also "
             "removes any basis for saying a task is outside the role, which is "
             "how hours creep past what you agreed to."),
        fix=("Duties are limited to the role stated in this letter; material "
             "additions are agreed in writing and reviewed against stipend and "
             "hours."),
        ask=("Can we keep the role description to what's in the letter, and treat "
             "anything bigger as a separate conversation?"),
    ),
    Rule(
        rid="fixed-hours-control",
        title="Set hours and a set week",
        category="control", severity=1, applies_to="employment",
        # A 5-day week is normal; six days, or a fixed clock-in/clock-out, is the
        # control that turns an internship into an unposted full-time job.
        any_of=[r"[6-7] days a week", r"6 days per week",
                r"from \d{1,2}[.:]\d{2}\s*(?:a\.?m\.?|p\.?m\.?) .{0,20}(?:to|[-–])\s*\d{1,2}[.:]\d{2}",
                r"available for \d+ hours on a daily basis",
                r"work schedule .{0,40}[6-7] days"],
        why=("Six days a week with fixed 11-to-8 hours is the schedule of a "
             "full-time job. It is not a complaint about effort, it is a "
             "calculation: divide the monthly stipend by the hours actually "
             "committed and see what the rate is."),
        fix=("Working hours are 5 days a week, or the stipend is set against the "
             "hours and days committed and reviewed if the schedule changes."),
        ask=("The schedule is six days -- can we look at the stipend against those "
             "hours, or move to five days?"),
    ),
    Rule(
        rid="location-at-discretion",
        title="Where you work can change at their discretion",
        category="control", severity=1, applies_to="employment",
        any_of=[r"working remotely until further notice",
                r"return to office date will be decided",
                r"(?:may|will be (?:required )?to) (?:relocate|shift to office|work from office)[^.]{0,60}(?:any time|notice|decision)",
                r"location .{0,40}(?:as determined|at the discretion|may change)"],
        why=("A remote offer that can become an office requirement at a date they "
             "choose later is a term you cannot plan around -- rent, college "
             "attendance and commute all depend on it. The change is legitimate; "
             "the unilateral timing is what needs a notice period."),
        fix=("Any change from remote to office requires 30 days' written notice, "
             "and the intern may decline without penalty if unable to relocate."),
        ask=("If it ever moves to office, can I get 30 days' notice and the option "
             "to decline?"),
    ),
    Rule(
        rid="ip-covers-all-related-work",
        title="They own anything you produce 'in relation to' them",
        category="ip", severity=3, applies_to="employment",
        any_of=[r"(?:all (?:the )?work|work product|output)[^.]{0,60}(?:at or in relation to|in relation to|connection with)[^.]{0,60}intellectual property",
                r"(?:shall|will|would) be the intellectual property of .{0,30}(?:company|eubrics|organization)",
                r"any and all (?:work|output|material)[^.]{0,60}(?:belong|vest|property of)"],
        none_of=[r"during (?:working )?hours[^.]{0,40}(?:using[^.]{0,20}(?:company|employer) (?:equipment|resources))?",
                 r"relating (?:to|with) the (?:purpose|services|scope)",
                 r"(?:does not include|excluding) .{0,60}(?:personal|own projects|coursework)"],
        why=("'At or in relation to' is far wider than 'within the scope of the "
             "services'. Read literally it reaches a side project you mention to "
             "your mentor, coursework, and an open-source commit that touches the "
             "same technology. For a developer building a public portfolio, that "
             "wording is the whole career risk."),
        fix=("Company owns work created within the scope of the assignment and "
             "using Company resources. Work created on your own time, without "
             "Company resources, and unrelated to the Company's business remains "
             "yours."),
        ask=("Can we limit the IP clause to work within scope or using company "
             "resources? I keep my own side projects and open-source work."),
    ),
    Rule(
        rid="public-sharing-ban",
        title="You may not write or talk about your work",
        category="ip", severity=2, applies_to="employment",
        any_of=[r"refrain from talking about your work in public",
                r"(?:not|prohibit|restrict)[^.]{0,60}(?:blogging|blog posts?|social networking|linkedln|linkedin|twitter)",
                r"without prior discussion and approval .{0,40}(?:mentor|manager|company)",
                r"shall not (?:write|post|publish|speak|disclose)[^.]{0,60}(?:blog|post|talk|presentation|conference)"],
        none_of=[r"(?:anonymised|aggregated|no confidential|no client data)",
                 r"after (?:public )?launch"],
        why=("For an early-career developer the public record of what you built is "
             "how you get hired next. A blanket ban on describing your own work -- "
             "online and 'offline among your friends, college' -- costs you that, "
             "and it is usually aimed at secrets, which a confidentiality clause "
             "already covers."),
        fix=("Intern may describe the work in general terms, and share non-"
             "confidential technical write-ups after launch or with the client "
             "name removed, provided no Company confidential information is disclosed."),
        ask=("Confidentiality I fully accept. Can I still describe what I worked "
             "on in general terms for my portfolio and blog?"),
    ),
    Rule(
        rid="byod-no-allowance",
        title="Your own machine, your own cost",
        category="money", severity=1, applies_to="employment",
        any_of=[r"stored on your (?:personal|own) (?:computer|laptop|machine|device)",
                r"using your own (?:computer|laptop|device|internet)",
                r"(?:arrange|provide) your own (?:laptop|system|internet)"],
        none_of=[r"(?:allowance|reimburse|equipment (?:provided|issued)|company laptop|company-issued)"],
        why=("Working on your own laptop and internet is normal in remote "
             "internships and is a real cost: depreciation, electricity, data, and "
             "the machine being inspected and wiped by an employer. It is worth "
             "priced into the stipend rather than absorbed silently."),
        fix=("Company provides equipment, or a monthly equipment and connectivity "
             "allowance of INR [amount]. Company data is confined to a dedicated "
             "account that can be removed cleanly at exit."),
        ask=("Since I'm on my own machine and connection, is there an equipment "
             "allowance? And can the work live in a separate profile so it's "
             "clean to remove at the end?"),
    ),
    Rule(
        rid="variable-pay-undefined",
        title="A large part of your pay depends on undefined targets",
        category="money", severity=2, applies_to="employment",
        any_of=[r"incentives? .{0,60}(?:vary|variable|depending|based on) .{0,40}(?:performance|target|achievement)",
                r"target[- ]based (?:job|role)", r"upto .{0,20}(?:incentive|bonus|reward)",
                r"evaluated based on (?:the )?target achievement"],
        none_of=[r"targets? (?:are|shall be) (?:set|defined|specified) .{0,40}(?:writing|schedule|annexure)",
                 r"(?:kpi|okr)[^.]{0,40}(?:defined|attached|schedule)"],
        why=("When a third of the money is 'up to' and tied to targets nobody has "
             "written down, the guaranteed number is the only real one. Quote "
             "yourself the fixed figure, and treat the incentive as unearned until "
             "the definition exists."),
        fix=("Targets and the incentive formula are issued in writing at the start "
             "of each month; the fixed stipend is payable regardless of targets."),
        ask=("What exactly is the target, and how is the incentive calculated? "
             "Until that's written I'll treat the fixed stipend as the number."),
    ),
    Rule(
        rid="unilateral-amendment",
        title="They can change the terms at any time",
        category="terms", severity=2, applies_to="employment",
        any_of=[r"terms and conditions[^.]{0,60}(?:may be )?amended from time to time",
                r"(?:company|employer) may (?:amend|change|modify|vary)[^.]{0,50}(?:terms|conditions|policy|policies)",
                r"as (?:the )?(?:company|management) (?:may )?(?:decide|determine|prescribe) from time to time"],
        none_of=[r"(?:with|upon) (?:prior )?(?:written )?(?:notice|consent) of the (?:employee|intern)",
                 r"no amendment .{0,40}(?:unless|except) .{0,40}in writing"],
        why=("If the employer can rewrite the agreement unilaterally, then nothing "
             "in it is a commitment -- including the stipend and the notice period. "
             "Policies legitimately change; the fix is notice and a right to leave "
             "rather than a silent rewrite."),
        fix=("Terms may be changed only on 30 days' written notice; if a change is "
             "materially adverse, the intern may resign without notice and be paid "
             "to the effective date."),
        ask=("Policies changing is fine, but can changes need 30 days' notice, with "
             "an option for me to exit if they're against me?"),
    ),
    Rule(
        rid="no-stipend-payment-date",
        title="No date your money is actually due",
        category="money", severity=2, applies_to="employment", doc_scope=True,
        any_of=[r"stipend .{0,60}(?:on or before|by the (?:\d+|last)|within \d+ days|payable on)",
                r"(?:paid|disbursed|credited) .{0,40}(?:on or before|by the (?:\d+|last)|within \d+ days)",
                r"(?:\d+(?:th|st|nd|rd)|last) day of each month"],
        why=("A monthly stipend with no payment date has no due date. In practice "
             "it arrives when the accounts team gets to it, and an intern with no "
             "invoice process has nothing to point at when it slips."),
        fix=("Stipend is credited on or before the 7th of the following month, and "
             "delay beyond 15 days accrues interest at 12% per annum."),
        ask=("Which date does the stipend actually land? Can we put it in writing "
             "as on or before the 7th?"),
    ),
    Rule(
        rid="no-grievance-route",
        title="No route to raise a problem",
        category="terms", severity=1, applies_to="employment", doc_scope=True,
        any_of=[r"grievance|escalat\w+|ombud|hr contact|ethics (?:line|policy)|whistle"],
        why=("Every clause in these documents names the reporting manager as "
             "evaluator, approver and the person you may not contradict. When the "
             "problem is the manager, there is nowhere to take it, and that is "
             "worth asking for precisely because it costs the employer nothing."),
        fix=("A named HR contact outside the reporting line is available for "
             "grievances, and no adverse action follows a good-faith report."),
        ask=("Who do I go to if the issue is with my mentor? Can we name an HR "
             "contact in the letter?"),
    ),
]
