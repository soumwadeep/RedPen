---
title: "A 1B model isn't smart enough to read a contract. So I never asked it to."
published: false
tags: devchallenge, hf26challenge, opensourceai, local_llm, contracts, privacy
---

*This is a submission for the [Hacktoberfest Open-Source AI Challenge Week 2: Side Hustle](https://dev.to/challenges/hacktoberfest-week2-2026-10-12).*

## What I built

**RedPen** is an offline contract reviewer for freelancers. You drop in a client agreement — PDF, DOCX, or pasted from an email — and it tells you which clauses will cost you money or time, quotes the exact words that triggered each finding, gives you wording to ask for, and drafts the negotiation email.

The person who'd pay for it is a designer or developer who just got a 9-page MSA from an agency and has three options: sign it unread, pay a lawyer $200–400 an hour to read it, or spend an evening googling "is pay when paid legal". RedPen is the fourth option, and it costs $19 once.

Here's what it found in a deliberately hostile sample agreement — a 2-page MSA that reads like a real one:

![RedPen review](https://raw.githubusercontent.com/soumwadeep/RedPen/main/assets/shot-full-review.png)

36 findings. Nine of them are things I'd call **STOP**: don't sign as written.

## Demo

The app is `redpen` on the command line, which starts a local model server and opens a browser UI bound to `127.0.0.1`.

![Model layer](https://raw.githubusercontent.com/soumwadeep/RedPen/main/assets/shot-model-layer.png)

That email at the bottom was written by the local model. It covers all six requested changes, in the freelancer's voice, and it's genuinely sendable.

To try it:

```bash
git clone https://github.com/soumwadeep/RedPen.git && cd RedPen
brew install llama.cpp
pip install -e .
redpen review samples/northgate_msa.pdf
```

## Code

https://github.com/soumwadeep/RedPen

## How I built it

There are two layers, and the whole design falls out of one decision: **the model never decides what is dangerous.**

**Layer 1 — 37 open rules, no model.** `redpen/rules/catalog.py` is a plain-Python library of freelance contract red flags: IP vesting on creation instead of on payment, assignment "whether or not payment has been made", pay-when-paid, Net 90, payment subject to "satisfaction", liquidated damages per day, unlimited liability, one-way consequential damages, post-term non-competes, unlimited revisions, evergreen renewal, confidentiality that swallows your general skills. Each rule carries its own plain-English explanation, a counter-clause you can paste, and the sentence to put in the email.

PyMuPDF extracts the text, clause segmentation recovers the numbering and keeps a page number and character span for every clause, and every finding cites the verbatim words that fired.

**Layer 2 — Gemma 3 1B via llama.cpp, for language only.** The model reads what layer 1 already found and writes it in the context of *this* contract: a three-line brief, a per-finding explanation, the negotiation email, and one pass at vagueness that patterns can't see ("Schedule A is undefined", "promptly means nothing").

That split isn't a hedge. A 1B model is not reliable enough to decide whether a clause is dangerous, and a rules engine is not good enough to write a persuasive email to a client. Each layer does the half it's actually competent at, and the report is complete even if the model is switched off entirely.

Running it: Gemma 3 1B at Q4_K_M, 769 MB, loads in 2.3 seconds, sits at about 0.83 GB resident on an **8 GB Apple Silicon MacBook** with no GPU and no Docker. The deterministic pass takes ~50 ms. A full review with the model layer takes 11–17 seconds.

### The guard-rails came from watching the model fail

A small local model fails in ways that would embarrass someone in front of a client, so its output is validated rather than trusted:

- **Citations are checked.** The model is asked to point at clauses. Anything that doesn't resolve to a clause number that actually exists in the document gets dropped. It often answers with the vague *word* it spotted ("reasonable") instead of a number, so I resolve that too — but only when that word appears in exactly one clause. Otherwise it's discarded rather than guessed.
- **Coverage is checked, format isn't.** My first email validator required a numbered list and rejected a perfectly good bulleted one. Now it checks whether the email actually represents the requested changes, by matching against the wording the user was told to ask for.
- **It invented a sign-off name.** Gemma signed several drafts "Max". The signature is now stripped and replaced with `[your name]`.
- **It mislabelled itself.** When I swapped the weights to Qwen to test model-independence, the UI still said the email came from "gemma" — because I'd hard-coded the string. The label now reads from the model that actually ran.
- **Every role has a deterministic fallback.** No engine, no parse, junk output: you still get a complete report and a usable template email.

## Why does open innovation matter?

For this product it isn't a philosophy, it's the business model. Four things that a closed API structurally cannot offer:

**1. The client's NDA never leaves the laptop.** That's the entire pitch. A freelancer's most sensitive document is the one describing work for the client who is *already* paying them — uploading it to a third party is exactly what they don't want, and "we promise to delete it in 30 days" is not the same as "it was never transmitted". This is enforced in code, not policy: the HTTP client raises if a base URL isn't loopback, so a stray environment variable can't turn a privacy product into an uploader. There's a test for that.

I'd rather prove it than assert it, so `scripts/offline_proof.sh` runs a full review — parse, rules, and the entire model pass — while sampling every socket the process holds:

```
· sockets observed during the run:
    19876 127.0.0.1:52704->127.0.0.1:8777
    19876 127.0.0.1:8795
    7599  127.0.0.1:8777->127.0.0.1:52704
✓ PASS -- every socket was loopback. Review score 99/99, no request left the machine.
```

Uploads are parsed from bytes and never written to disk. The last eight reviews live in a bounded in-memory cache. The UI and the exported brief contain no remote `src` or `href` — a test fails if one appears. (The first version of this script passed by observing *zero* sockets, because I built the PID list with literal parentheses and `lsof` never got a valid argument. A proof that looks at nothing proves nothing.)

**2. Zero marginal cost makes a one-time price survivable.** I looked at hosting. A box big enough to hold the weights is roughly $25/month for 2–5 tokens per second on shared CPU — slower than the user's own laptop, and every contract uploaded lands on a server the freelancer doesn't control. That's the worst of both. Locally, user #500 costs me nothing, which is what lets this be $19 once instead of a subscription that has to defend a per-seat API bill.

**3. The rules are editable, which is the actual moat.** If you edit video, "perpetual, all-media, universe-wide usage rights" is a red flag you know and no general-purpose API reliably flags. You can add it as a JSON file in `~/.redpen/rules/` — no code, no re-approval from anyone:

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

With a closed model you can't see the standard being applied, and you can't change it. Here a lawyer could audit all 37 rules in an afternoon, and a niche community can maintain its own fork for its own trade.

**4. Swapping models is a config line, so nobody's pricing page is my cost base.** Verified, not assumed: I ran the same contract under Gemma 3 1B and Qwen 2.5 1.5B. The 12 findings were **identical** — same rules, same pages, same evidence — and only the brief and the email changed. That's the payoff of keeping judgement out of the model: model choice is a wording preference, not a correctness risk.

## What the tests caught

64 tests, no model required, plus one that exercises the real local model.

The important one is precision. I wrote a genuinely fair contractor agreement — IP on payment, 40% deposit, Net 14, mutual liability cap, background-IP carve-out, portfolio rights, 30-day notice both ways — and RedPen initially flagged **five false positives** on it. The root cause was systematic: the engine matched "payment is **not** contingent on Client's receipt of funds" as a pay-when-paid trap. Reading a phrase in order to *refuse* it is not the same as asserting it, so matching is now negation-aware, and "No deposit shall be made" is reported as *expressly refused* rather than credited as having a deposit clause.

That distinction is the product. A tool that cries wolf gets uninstalled after it wastes an evening on a good contract.

Two other bugs worth mentioning because the tests are what found them: uploads were losing their file extension, so PDFs fell through to the plain-text branch and were parsed as binary garbage into 154 nonsense clauses — file type is now sniffed from magic bytes. And a dropped import made every API request 500 while all 20 unit tests stayed green, because `to_dict()` was only ever reached through the server.

## Limits, honestly

- **8 GB RAM is the floor.** 1–3B models at Q4 fit. 7B does not. Close Chrome.
- **Scanned PDFs aren't supported.** There's no selectable text, and RedPen won't send your pages to an OCR service. It says so rather than returning an empty review.
- **The model layer is a 1B model.** Its explanations are sometimes generic — it will tell you that losing work "could result in lost revenue". The library's own wording is always underneath it for exactly this reason.
- **A clean report is weak evidence.** No rule matched is not a guarantee the contract is fair, and the UI says that out loud rather than letting a green gauge imply safety.
- **Jurisdictions differ.** These are commercial risk patterns, not legal advice, and a clause unenforceable in one country is standard in another.

## My first user

<!-- TODO: fill in after handing it to 2-3 freelancers. Do not publish this
     section with invented results. If nobody has run it yet, delete the
     section -- the challenge says it is optional, and a fabricated first user
     would undercut everything else in this post. -->

## Prize categories

**Best Use of Gemma.** Gemma 3 1B (instruct) is the default and only shipped model: `ggml-org/gemma-3-1b-it-GGUF`, Q4_K_M, downloaded on first run, served by llama.cpp on loopback. It writes the brief, the per-finding explanations, the negotiation email and the ambiguity pass. It's the model that makes this fit in 8 GB of RAM and cost nothing per review — which is the whole reason the privacy promise is possible.

---

RedPen is MIT licensed. It is a pattern-matching tool with an open rule library, not a lawyer.
