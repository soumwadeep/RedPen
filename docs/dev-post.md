---
title: "A 1B model isn't smart enough to read a contract. So I never asked it to."
published: false
tags: devchallenge, hf26challenge, ai, opensource, privacy
---

*This is a submission for the [Hacktoberfest Open-Source AI Challenge Week 2: Side Hustle](https://dev.to/challenges/hacktoberfest-week2-2026-10-12)*

## What I Built

**RedPen** is an offline contract reviewer for freelancers. You drop in an agreement — PDF, DOCX, or pasted from an email — and it tells you which clauses will cost you money or time, quotes the exact words that triggered each finding, gives you wording to ask for, and drafts the negotiation email.

The person who'd pay for it is a developer or designer who just got a nine-page MSA and has three options: sign it unread, pay a lawyer $200–400 an hour, or spend an evening googling "is pay-when-paid enforceable". RedPen is the fourth option, and it costs $19 once.

It runs entirely on your laptop. Open-weight model, open rule library, no account, no API key, no upload. A client's NDA never lands on a server you don't control, because it never leaves the machine.

## Demo

A deliberately hostile agency MSA — 2 pages, 687 words:

![Verdict](https://raw.githubusercontent.com/soumwadeep/RedPen/main/assets/shot-01-verdict.png)

**36 findings**, nine STOP. The panel under the gauge isn't the model guessing — it's the numbers the contract actually states, pulled out with regex: Net 90, no deposit, 7-day notice, unlimited revisions, Delaware.

Every finding cites its evidence, so you can check the tool's work against the page:

![Evidence](https://raw.githubusercontent.com/soumwadeep/RedPen/main/assets/shot-02-evidence.png)

Then the local model writes the email you actually send:

![Email](https://raw.githubusercontent.com/soumwadeep/RedPen/main/assets/shot-03-email.png)

And the test that matters most — a genuinely fair contractor agreement, which comes back empty:

![Clean](https://raw.githubusercontent.com/soumwadeep/RedPen/main/assets/shot-04-clean.png)

A tool that cries wolf gets uninstalled the first time it wastes an evening on a good contract.

And an internship offer letter, where the header reads `DOC OFFER LETTER OR EMPLOYMENT
TERMS` and the amber panel counts the fields nobody has filled in yet:

![Offer letter](https://raw.githubusercontent.com/soumwadeep/RedPen/main/assets/shot-06-offer-letter.png)

Different document, different questions. An unscoped library tells an intern they are
missing a deposit clause; a scoped one tells them their original degree certificates
are being held by the employer.

```bash
git clone https://github.com/soumwadeep/RedPen.git && cd RedPen
brew install llama.cpp
pip install -e .
redpen                       # opens http://127.0.0.1:8790
redpen review contract.pdf   # or from the terminal
```

**Video demo:** <!-- TODO: paste your 60s Loom/YouTube link -->

## Code

https://github.com/soumwadeep/RedPen

MIT licensed. 65 rules, 98 tests, no compiled Python bindings to break on install.

```
redpen/
  ingest.py           PDF/DOCX/text -> clauses with page + span grounding
  doctype.py          what kind of document is this, and what's still blank
  rules/catalog.py    37 freelance / B2B red flags
  rules/employment.py 18 offer-letter and internship red flags
  rules/nda.py        10 confidentiality red flags
  engine.py           matching, negation, evidence, dates, scoring
  llm.py              loopback-only OpenAI-compatible client + small-model hygiene
  narrate.py          brief, explanations, negotiation email, ambiguity pass
  server.py           FastAPI on 127.0.0.1, in-memory only
```

## How I Built It

Two layers, and the whole design follows from one decision: **the model never decides what is dangerous.**

**Layer 1 is 65 open rules and no model.** Each rule carries its own plain-English explanation, a counter-clause you can paste, and the sentence to say in the email. PyMuPDF extracts the text, segmentation recovers clause numbering and keeps a page number and character span for every clause, and every finding quotes the verbatim words that fired.

**Layer 2 is Gemma 3 1B via llama.cpp, for language only.** It reads what layer 1 already found and rewrites it in the context of *this* contract: a three-line brief, a per-finding explanation, the negotiation email, and one pass at vagueness patterns can't see.

That split isn't modesty about small models. A 1B model is not reliable enough to decide whether a clause is dangerous, and a rules engine is not good enough to write a persuasive email to a client. Each layer does the half it's actually competent at, and the report is complete with the model switched off entirely.

Running on an **8 GB Apple Silicon MacBook**, no GPU, no Docker: Gemma 3 1B at Q4_K_M, 769 MB, loads in 2.3 s, sits at 0.83 GB resident. The rule pass takes 12–28 ms after ~8 ms to parse; a full review with the model layer takes 11–17 seconds. Findings render immediately and the model's work streams in over SSE, so nothing blocks on a small model writing an email.

### Then I fed it my own paperwork

Everything above was built against synthetic contracts I wrote myself. Then I ran it on six real documents — two internship offer letters, an offer letter with an NDA, and a freelance agreement — and it failed in ways my own samples could not have.

**It silently discarded page 1.** Segmentation only emitted text *after* the first numbered clause. In a real offer letter, page 1 is unnumbered prose and page 2 is the numbered list — so the unpaid training period, the 6-day week and the 11am–8pm schedule were never analysed at all. The tool reported a tolerable score on a document whose worst terms it had thrown away. Fixed with a preamble clause.

**It gave an intern financial advice meant for a freelancer.** Asked about an offer letter, the freelance library reported that they had no deposit clause, no late-payment interest and no right to suspend work. True, worthless, and printed directly above the real finding: **the employer was keeping their original degree certificates**, with a clause requiring an HR-approved "replacement document" to get one back. That's what document typing is for — rules now declare which document types they run against.

**A real letter had impossible dates.** One internship was dated 29/06/2023 for a term that started 3-Jul-2022 and ended 28-Apr-2023 — finished before the offer was written. No keyword rule can see that, so dates are now parsed in six formats and cross-checked.

**Perpetual confidentiality was hiding in plain sight.** An NDA ended its obligations "until such time as all Confidential Information becomes publicly known" — which is never. A search for `perpetual|indefinitely` walks straight past it. The same document had an uncapped indemnity for the disclosing party's legal fees buried in the *injunctive relief* clause of an NDA, which is exactly where nobody looks.

**A missing word boundary created a false positive.** "The Freelancer will not incur new expenses without approval" — sensible drafting — was flagged as expense denial, because an unanchored `no` matched inside `not`.

**And a template full of blanks was reported as a hostile deal.** `[city, state] will have exclusive jurisdiction` fired the venue rule at full severity. Unfilled fields are now counted, shown in their own panel, and any finding whose trigger text is still a blank gets demoted: an unfinished draft is not a decision being made against you.

Six real documents, six bugs. That's the loop this architecture is built for — when it misjudges a document type, the fix is a rule, not a re-training run or a support ticket.

### Guard-rails from watching the model fail

Citations are resolved against clauses that exist and dropped otherwise; the model often answers with the vague *word* it spotted rather than a number, so that's resolved too, but only when it appears in exactly one clause. Emails are validated for coverage of the requested changes, not format — my first validator rejected a perfectly good bulleted email for not being numbered. It invented a sign-off name ("Max"), so signatures are stripped. And when I swapped weights to test model-independence, the UI still claimed "gemma" while Qwen had written it: the label was hard-coded, and now it reads from the model that actually ran.

## Why Does Open Innovation Matter?

Four things a closed API structurally can't offer.

**1. The client's NDA never leaves the laptop.** A freelancer's most sensitive document is the one describing work for the client who is *already* paying them, and "we promise to delete it in 30 days" is not the same as "it was never transmitted". Enforced in code, not policy: the HTTP client raises if a base URL isn't loopback, so a stray environment variable can't turn a privacy tool into an uploader. Uploads are parsed from bytes and never written to disk; the last eight reviews live in a bounded in-memory cache; the UI and exported brief contain no remote `src` or `href`.

`scripts/offline_proof.sh` runs a full review while sampling every socket the process holds:

```
· sockets observed during the run:
    19876 127.0.0.1:52704->127.0.0.1:8777
    19876 127.0.0.1:8795
    7599  127.0.0.1:8777->127.0.0.1:52704
✓ PASS -- every socket was loopback. Review score 99/99, no request left the machine.
```

The first version of that script passed by observing *nothing*, because I built the PID list with literal parentheses and `lsof` never got a valid argument. A proof that looks at nothing proves nothing, so it now prints what it saw.

**2. Zero marginal cost is what makes a one-time price survivable.** I looked at hosting. A box big enough for the weights is roughly $25/month for 2–5 tokens/second on shared CPU — slower than the user's own laptop, and every contract uploaded lands on a server the freelancer doesn't control. Worst of both. Locally, user #500 costs nothing extra, so this can be $19 once instead of a subscription defending a per-seat API bill.

**3. The rules are editable, which is the actual moat.** If you edit video, "perpetual, all-media, universe-wide usage rights" is a red flag you know and no general API reliably flags. You add it as a JSON file in `~/.redpen/rules/` — no code, no approval:

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

With a closed model you can't see the standard being applied, and you can't change it. Here a lawyer could audit all 65 rules in an afternoon, and a niche community can maintain its own fork for its own trade.

**4. Swapping models is a config line, so nobody's pricing page is my cost base.** Verified: the same contract under Gemma 3 1B and Qwen 2.5 1.5B produced **identical findings** — same rules, same pages, same evidence — only the brief and email changed. That's the payoff of keeping judgement out of the model: choosing weights becomes a wording preference, not a correctness risk.

**Where open beat closed, specifically:** a hosted API would have been better at prose and worse at the product. It cannot promise the document never left the machine, cannot let a user encode their own trade's traps, makes per-review cost non-zero, and its judgement is unauditable. The thing it was better at — writing — is the half I deliberately gave away.

**Limits, honestly.** 8 GB RAM is the floor: 1–3B at Q4 fit, 7B doesn't. Scanned PDFs aren't supported — no selectable text, and RedPen won't send your pages to an OCR service, so it says so rather than returning an empty review. The model layer is a 1B model and its explanations are sometimes generic, which is why the library's wording is always underneath. A clean report is weak evidence: no rule matched is not a guarantee the contract is fair, and the UI says that out loud instead of letting a green gauge imply safety. And the library is written from a freelancer's and an intern's point of view — it flags commercial risk patterns, not legal validity, across jurisdictions it does not claim to know.

RedPen is a pattern-matching tool with an open rule library, not a lawyer.

## My Agent Session

Built agent-assisted, with the agent doing the typing and me owning the claims. Seven tracked milestones: verify the model runs on 8 GB before designing around it, build the rule library, wire the narration, build the app, add tests and samples, package it, write this post.

The session log is honest about two things a summary wouldn't be. The first architecture sketch assumed a hosted web version, and the cost and privacy math above is what killed it. And most of the bugs listed under "Then I fed it my own paperwork" were *introduced by the agent* during this session and found by tests written in the same session — including a validation script that passed by observing nothing.

<!-- Optional: publish this session to DevRelay and embed it with the agent_session tag. -->

## Prize Categories

**Best Use of Gemma.** Gemma 3 1B (instruct) is the default and only shipped model — `ggml-org/gemma-3-1b-it-GGUF`, Q4_K_M, downloaded on first run, served by llama.cpp on loopback. It writes the brief, the per-finding explanations, the negotiation email and the ambiguity pass. It's the model small enough to fit in 8 GB of RAM and cost nothing per review, which is the precondition for the privacy promise being true rather than a policy.

---

MIT licensed. Model weights stay under their own licences — RedPen ships none, it downloads them for you.
