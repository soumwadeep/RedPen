---
title: "A 1B model isn't smart enough to read a contract. So I never asked it to."
published: false
tags: devchallenge, hf26challenge, ai, opensource, privacy
cover_image: https://raw.githubusercontent.com/soumwadeep/RedPen/main/assets/cover.png
---

*This is a submission for the [Hacktoberfest Open-Source AI Challenge Week 2: Side Hustle](https://dev.to/challenges/hacktoberfest-week2-2026-10-12)*

**TL;DR** — RedPen is an offline contract reviewer for freelancers. 65 open rules decide what is dangerous; a local Gemma 3 1B model only rewrites that into language you can send. Nothing uploads, nothing costs per review, and $19 once is a survivable price *because* the model runs on the user's own laptop.

## What I Built

A developer who just received a nine-page MSA has three options: sign it unread, pay a lawyer $200–400 an hour, or spend an evening googling "is pay-when-paid enforceable".

RedPen is the fourth option. Drop in an agreement — PDF, DOCX, or pasted from an email — and it returns the clauses that will cost you money or time, **quotes the exact words that triggered each one**, gives you replacement wording, and drafts the negotiation email. It runs entirely on your laptop: open weights, open rules, no account, no API key, no upload.

The buyer is any independent who signs things. The pitch is one sentence: *your client's NDA never leaves your machine, because it never goes anywhere.*

## Demo

**Demo — the whole review, from drop to drafted email.** Captured headlessly at
progressive points while Gemma streamed over loopback: the 36 findings land first
(the rule pass is ~20 ms), then the brief, then the explanations, then the email.
Reproducible with `python3 scripts/build_demo.py`.

![RedPen demo](https://raw.githubusercontent.com/soumwadeep/RedPen/main/assets/demo.gif)

Full-resolution MP4: [assets/demo.mp4](https://raw.githubusercontent.com/soumwadeep/RedPen/main/assets/demo.mp4) 

A deliberately hostile agency MSA — 2 pages, 687 words:

![Verdict](https://raw.githubusercontent.com/soumwadeep/RedPen/main/assets/shot-01-verdict.png)

**36 findings**, nine of them STOP. The strip under the gauge isn't the model guessing — it's the numbers the contract actually states, pulled out with regex: Net 90, no deposit, 7-day notice, unlimited revisions, Delaware.

Every finding cites its source, so you can check the tool's work against the page:

![Evidence](https://raw.githubusercontent.com/soumwadeep/RedPen/main/assets/shot-02-evidence.png)

Then the local model writes the email you'd actually send:

![Email](https://raw.githubusercontent.com/soumwadeep/RedPen/main/assets/shot-03-email.png)

And the result that matters most — a genuinely fair contractor agreement, which comes back empty:

![Clean](https://raw.githubusercontent.com/soumwadeep/RedPen/main/assets/shot-04-clean.png)

A tool that cries wolf gets uninstalled the first time it wastes an evening on a good contract.

And an internship offer letter, where the header reads `DOC OFFER LETTER OR EMPLOYMENT TERMS`
and the amber panel counts fields nobody has filled in. Different document, different rules:

![Offer letter](https://raw.githubusercontent.com/soumwadeep/RedPen/main/assets/shot-06-offer-letter.png)

The top STOP finding on that page is *"The start date is before the letter itself"* — a date
anomaly no keyword rule could catch — and below it, that the employer holds the intern's
original degree certificates.

```bash
git clone https://github.com/soumwadeep/RedPen.git && cd RedPen
brew install llama.cpp && pip install -e .
redpen                       # opens http://127.0.0.1:8790
```
## Code

**[github.com/soumwadeep/RedPen](https://github.com/soumwadeep/RedPen)** — MIT, 4,092 lines of app code and 2,200 lines of tests, 65 rules, 191 tests, no compiled bindings to break on install.

## How I Built It

One decision drives everything: **the model never decides what is dangerous.**

**Layer 1 — 65 open rules, no model.** Plain Python in `redpen/rules/`, in three libraries: freelance agreements, offer letters and internships, NDAs. Each rule carries its own explanation, a counter-clause you can paste, and the sentence to say in the email. PyMuPDF extracts the text, segmentation recovers clause numbering and keeps a page number and character span for every clause, and every finding quotes verbatim words.

**Layer 2 — Gemma 3 1B via llama.cpp, language only.** It reads what layer 1 already found and rewrites it for *this* contract: a three-line brief, a per-finding explanation, the negotiation email, and one pass at vagueness patterns can't see.

That split isn't modesty about small models. A 1B model is not reliable enough to judge a clause, and a rules engine is not good enough to write a persuasive email to a client. Each layer does the half it is actually competent at — and the report is complete with the model switched off entirely.

It runs on an **8 GB Apple Silicon MacBook**, no GPU, no Docker: 769 MB of weights, 2.3 s to load, 0.83 GB resident. The rule pass takes 12–28 ms; a full review with the model layer, 11–17 s. Findings render instantly and the model's work streams in over SSE, so nothing blocks on a small model composing an email.

### Then I fed it my own paperwork

Everything above was built against synthetic contracts I wrote myself. Then I ran it on six real documents — two internship letters, an offer letter with an NDA, an onboarding checklist, a freelance agreement — and it failed in ways my own samples could not have produced.

| What it got wrong | Why it matters |
| --- | --- |
| **Silently discarded page 1** of an offer letter | Segmentation only emitted text *after* the first numbered clause. In real offer letters page 1 is unnumbered prose — so the unpaid training period and the 6-day, 11am–8pm schedule were never analysed. It scored a document whose worst terms it had thrown away. |
| **Told an intern they had no deposit clause** | Freelance rules ran on employment terms: no deposit, no late-payment interest, no right to suspend. True, worthless — and printed directly above the real finding, which was that the employer was **holding their original degree certificates**. |
| **Missed impossible dates** | One internship was offered on 29/06/2023 for a term that started 3-Jul-2022 and ended 28-Apr-2023 — finished before the offer was written. No keyword rule can see that, so dates are now parsed in six formats and cross-checked. |
| **Missed disguised perpetuity** | An NDA ended its obligations "until all Confidential Information becomes publicly known" — never. A search for `perpetual\|indefinitely` walks straight past it. The same document buried an uncapped indemnity for the other side's legal fees inside the *injunctive relief* clause. |
| **Flagged sane drafting** | "The Freelancer will not incur new expenses without approval" fired the expense-denial rule, because an unanchored `no` matched inside `not`. |
| **Read blanks as hostility** | `[city, state] will have exclusive jurisdiction` scored at full severity. Unfilled fields are now counted, shown as their own panel, and any finding triggered by a blank is demoted — an unfinished draft is not a decision being made against you. |

Six real documents, six bugs. That's the loop this architecture exists for: when it misjudges a document type, the fix is a rule, not a retraining run or a support ticket.

### Guard-rails, all learned from the model failing

| Failure | Guard |
| --- | --- |
| Cites a clause that doesn't exist | Resolved against real clauses, else dropped. It often answers with the vague *word* it spotted instead of a number, so that's resolved too — but only when the word appears in exactly one clause. |
| Drops three of your six asks | Coverage checked against the wording you were told to request. Format is not checked: my first validator rejected a perfectly good bulleted email for not being numbered. |
| Signs your email "Max" | Stripped and replaced with `[your name]`. |
| Claims to be a model it isn't | When I swapped weights to test model-independence, the UI still said "gemma" while Qwen had written it. The label was hard-coded; now it reads from the model that ran. |
| Returns junk, or no engine is running | Every role has a deterministic fallback, so the report is always complete. |

## Why Does Open Innovation Matter?

Four things a closed API structurally cannot offer.

**1. The client's NDA never leaves the laptop.** A freelancer's most sensitive document is the one describing work for the client who is *already* paying them. "We promise to delete it in 30 days" is not the same as "it was never transmitted." This is enforced in code, not policy: the HTTP client raises if a base URL isn't loopback, so a stray environment variable cannot turn a privacy tool into an uploader — there's a test for that. Uploads are parsed from bytes and never written to disk; the last eight reviews live in a bounded in-memory cache; the UI and exported brief contain no remote `src` or `href`.

`scripts/offline_proof.sh` runs a full review while sampling every socket the process holds:

```
· sockets observed during the run:
    19876 127.0.0.1:52704->127.0.0.1:8777
    7599  127.0.0.1:8777->127.0.0.1:52704
✓ PASS -- every socket was loopback. Review score 99/99, no request left the machine.
```

The first version of that script passed by observing *nothing*, because I built the PID list with literal parentheses and `lsof` never got a valid argument. A proof that looks at nothing proves nothing, so it now prints what it saw.

**2. Zero marginal cost is what makes a one-time price survivable.** I looked at hosting. A box big enough for the weights runs about $25/month for 2–5 tokens/second on shared CPU — slower than the user's own laptop, with every contract landing on a server they don't control. Worst of both. Locally, user #500 costs nothing extra, which is what lets this be $19 once instead of a subscription defending a per-seat API bill.

**3. The rules are editable, which is the actual moat.** If you edit video, "perpetual, all-media, universe-wide usage rights" is a red flag you know and no general API reliably flags. You add it as JSON in `~/.redpen/rules/` — no code, no approval:

```json
[{
  "id": "all-media-perpetual-usage",
  "title": "Usage rights are unlimited",
  "category": "ip", "severity": 3,
  "why": "A perpetual all-media licence is a different price than a 12-month single-platform run.",
  "fix": "Usage is limited to one platform for 12 months; further usage is priced per the rate card.",
  "ask": "Which platforms, and for how long? That changes the fee.",
  "any_of": ["all media", "any media now known or hereafter devised", "perpetual licen"],
  "all_of": [["usage", "licen", "rights"]]
}]
```

With a closed model you cannot see the standard being applied, and you cannot change it. Here a lawyer could audit all 65 rules in an afternoon, and a community can maintain its own fork for its own trade.

**4. Swapping models is a config line, so nobody's pricing page is my cost base.** Verified: the same contract under Gemma 3 1B and Qwen 2.5 1.5B produced **identical findings** — same rules, same pages, same evidence — only the brief and the email changed. That's the payoff of keeping judgement out of the model: choosing weights becomes a wording preference, not a correctness risk.

**Where open beat closed, specifically:** a hosted API would have been better at prose and worse at the product. It cannot promise the document never left the machine, cannot let a user encode their own trade's traps, makes per-review cost non-zero, and its judgement is unauditable. The thing it was better at — writing — is the half I deliberately gave away.

### Results, including the ones that hurt

| Document | Type detected | Findings | Score |
| --- | --- | --- | --- |
| Hostile agency MSA (synthetic) | services | 36 | 99 |
| Typical design gig (synthetic) | services | 12 | 83 |
| **Fair contractor deal (synthetic)** | services | **0** | **0** |
| Internship offer letter (synthetic) | employment | 20 | 97 |
| One-way NDA (synthetic) | nda | 11 | 77 |
| Real offer letter (Skolar) | employment | 12 | 90 |
| Real internship letter (Pentonix) | employment | 8 | 77 |
| Real offer letter (Eubrics) | employment | 12 | 85 |
| Real NDA (Eubrics) | nda | 11 | 77 |
| Real onboarding checklist | *not an agreement* | 0 | refused |
| Real freelance template | services | 3 | 18 |

Five synthetic fixtures, six real documents. The fair contract scoring zero and the
checklist being refused are the two rows I would defend hardest: an instruction list
makes no promises, and scoring it would have manufactured findings out of prose.

### What two comments on this post changed

I published before this was as tested as it should have been, and two comments
in the first day were more useful than anything I had written myself.

**@ArhanCanli** pointed out that my six real documents had quietly become my
training set — every fix was written to make a document I had already opened come
out right — and suggested minimal pairs: the same clause asserted and refused, to
see which rules actually survive negation. That test is now
`tests/test_negation_pairs.py`, 30 pairs, and **it found five over-flag bugs the
first time it ran.** The best one: the negation look-back window was 52
characters, so in "Nothing in this Agreement shall make the Contractor's
liability unlimited" it scanned "othing", found no negator, and flagged a clause
that refuses the very thing it is being accused of. Fixing it properly meant
abandoning character windows altogether and cutting at clause boundaries —
punctuation and conjunctions — because "Nothing shall *limit* liability, which is
unlimited" contains a negator that governs the wrong verb.

They also noted that `lsof` sampling can miss a connection that opens and closes
between samples, which is true, and that my fair-contract result was one data
point. Both are now addressed: `tests/test_offline_enforcement.py` intercepts
`socket.connect` for the duration of a whole review and raises on any non-loopback
target, so the property is enforced rather than observed, and
`tests/test_precision_variants.py` holds eight fair drafts across five
jurisdictions, seven of them paired with a near-miss where one hostile clause is appended.

That second file immediately found four more gaps, all in the *absence* detectors:
a liability cap written as "is limited to the fees paid" was not recognised as a
cap, a deposit "payable on signature" was not recognised as a deposit, a
translation memory retained by the translator was not recognised as a tooling
carve-out, and a normal five-day week was being flagged as employee-style
control. Writing more good contracts turned out to be a better test than writing
more bad ones.

**@IliaIvanov** described the same failure in their own cold-email checker — a
small model inventing an opt-out that was not there — which is exactly why every
quote in RedPen must appear verbatim in the source document, asserted by a test
that walks every finding and checks the string exists in the text. Their question,
"do you run the rules against fair contracts to count false alarms, or mostly
against hostile ones?", had an uncomfortable answer when I wrote it down: mostly
hostile, and one fair file. It now has eight, plus a control case proving a clean
result is not just the rules being asleep.

One thing I did not do: quietly delete the cases the new tests could not pass.
Four limitations are now encoded as tests that **fail if someone fixes them
without updating the list** — statutory carve-outs read as unlimited liability,
legally mandated insurance, a negator two promises earlier in the same
comma-joined sentence, and the "nothing shall limit liability, which is
unlimited" construction above. A limitation you can see is worth more than one I
have quietly tuned away.

**Limits, honestly.** 8 GB RAM is the floor — 1–3B at Q4 fit, 7B doesn't. Scanned PDFs aren't supported: no selectable text, and RedPen won't send your pages to an OCR service, so it says so rather than returning an empty review. The model layer is a 1B model and its explanations are sometimes generic, which is why the library's own wording sits underneath it. A clean report is weak evidence — no rule matched is not a guarantee of fairness, and the UI says that out loud instead of letting a green gauge imply safety. And the library is written from a freelancer's and an intern's point of view: it flags commercial risk patterns, not legal validity, across jurisdictions it does not claim to know.

RedPen is a pattern-matching tool with an open rule library, not a lawyer.

## My Agent Session

Built agent-assisted — the agent did the typing, I owned the claims. The work log is committed at **[docs/agent-session.md](https://github.com/soumwadeep/RedPen/blob/main/docs/agent-session.md)**: every milestone mapped to a commit, and every mistake listed with the test that caught it.

Two things that log is honest about which a summary wouldn't be. The first architecture sketch assumed a hosted web version, and the cost and privacy math above is what killed it. And most of the bugs in the failure table were *introduced by the agent during this session* and caught by tests written in the same session — including a validation script that passed by observing nothing.

## My First User

Shreshtha Das, a freelance developer who tests tools like this, ran RedPen on a real agreement. His feedback, verbatim:

> As a freelance tester, I tested **RedPen** and found it to be a genuinely useful tool for freelancers who want to understand their contracts before signing them. I tried reviewing an agreement and was impressed by how clearly it highlighted potentially risky clauses, quoted the exact wording that needed attention, and suggested more freelancer-friendly alternatives. The negotiation email draft was another helpful feature, as it made it easier to communicate concerns professionally without spending hours figuring out what to say. I especially liked that RedPen works entirely offline, which is a major advantage when dealing with confidential client agreements and NDAs. Overall, RedPen makes contract review more accessible, saves valuable time, and gives freelancers more confidence when negotiating terms with clients. It's a practical tool that I can see myself recommending to other developers, designers, and independent professionals.

I'd rather keep two things in view than round them off. He reviewed one agreement, so this is a single data point, not validation — and the one thing I most wanted from him, **a false positive**, is the thing he didn't report. Precision is the claim this tool can least afford to get wrong, and it's the reason the fair-contract test exists.

What he did confirm is the part enforced in code rather than promised in a README: that the offline behaviour holds, and that it matters most exactly where he says it would — client agreements and NDAs.

**Did he pay?** Yes — ₹89, which is more than ₹0 and less than the $19 I'm asking. The honest read is that a friend paid something to be supportive, not that a stranger paid a price. The next test is someone with no reason to be kind.

**A second voice — from someone who read the project, not someone who used it.** The founder of [Actizant](https://actizant.com/), which builds what they call intelligent operating systems for rural India, wrote this after reviewing the repo:

> "Privacy should be a fundamental design principle, not an afterthought, especially when dealing with confidential client agreements, statements of work, and NDAs."

They also handed me a roadmap in three lines, which is more useful than praise: **customisable risk rules per profession**, **jurisdiction-aware guidance**, and **transparent statements of what automated analysis cannot do**. The first two are exactly what an open rule library is built for — a profession-specific rule set is a JSON file, and a jurisdiction profile is a second rule set with different safe-harbours. The third is why the UI says "no rule matched is not a guarantee of fairness" instead of showing a green tick.

## Prize Categories

**Best Use of Gemma.** Gemma 3 1B (instruct) is the default and only shipped model — `ggml-org/gemma-3-1b-it-GGUF`, Q4_K_M, downloaded on first run and served by llama.cpp on loopback. It writes the brief, the per-finding explanations, the negotiation email and the ambiguity pass. It is the model small enough to fit in 8 GB of RAM and cost nothing per review, which is the precondition for the privacy promise being true rather than a policy.

---

MIT licensed. Model weights stay under their own licences — RedPen ships none, it downloads them for you.
