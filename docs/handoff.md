# Handoff kit

Two things to finish before Saturday 23:59 PDT: land one real user, and record
60 seconds of screen. Both are written out below so you can act without
re-deciding anything.

---

## 1. Send this

Copy-paste, edit the greeting. Send to 3–5 freelancers, not one — you need two
of them to reply.

> Got a minute? I built a small tool and I want it to fail in front of someone
> who actually signs contracts, not in front of me.
>
> It's **RedPen** — you drop in a client agreement (PDF, DOCX, or paste the
> text) and it flags the clauses that routinely cost freelancers money: IP
> transferring before you're paid, pay-when-paid, Net 90, "until the client is
> satisfied", unlimited revisions, uncapped liability, post-term non-competes.
> For each one it quotes the exact words, tells you why it hurts, gives you
> wording to ask for, and drafts the negotiation email.
>
> The point is that it runs entirely on your laptop — an open 1B model
> (Gemma 3) plus a library of 37 rules I wrote. Nothing uploads anywhere, so a
> client's NDA never lands on a server. No account, no API key, works on a
> plane.
>
> Install (~2 minutes, needs Homebrew and about 1 GB for the model):
>
> ```
> git clone https://github.com/soumwadeep/RedPen.git && cd RedPen
> brew install llama.cpp
> pip install -e .
> redpen
> ```
>
> That opens it in your browser. Or from the terminal:
> `redpen review your-contract.pdf`
>
> **Two asks:**
> 1. Run one real contract through it — one you've already signed is fine and
>    honestly better.
> 2. Tell me: did it catch something you'd have missed? Did it flag anything
>    that was actually fine? And would you have paid $19 for this before you
>    signed?
>
> It's not legal advice — it's a checklist with teeth. If it says a clause is
> fine, that's weak evidence, not a guarantee.

If they don't want to install anything, the fallback that still counts: ask
them to email you a contract they signed, run it yourself, and read the result
together on a 10-minute call. That gives you the same three answers.

### The three questions, verbatim

Ask these exactly — they map to the sections the judges read.

1. **Did it catch something you would have missed?** (Does it work?)
2. **Did it flag anything that was actually fine?** (Precision — the failure
   mode that kills trust. This is the one I most want, even if the answer is
   embarrassing.)
3. **Would you pay $19 once for this? What would make it $49?** (Would anyone?)
4. Bonus: **"What did you ask for that wasn't there?"** — that's the roadmap and
   it's the best line to end a submission post on.

### What to do with a false positive

If it cries wolf, that's the most valuable outcome available. Open
`redpen/rules/catalog.py`, find the rule that fired, and add the safe-harbour
phrase to its `none_of` list — then add the sentence that fooled it as a case in
`tests/test_engine.py`. That's a five-minute fix and it's exactly the loop the
open rule library exists to enable. Note it in the post; a documented false
positive you fixed is stronger than a claim of perfect precision.

---

## 2. Record this (optional — a GIF demo is already in the post)

`python3 scripts/build_demo.py` regenerates `assets/demo.gif` and `assets/demo.mp4`
from live captures of the running app. Those are already embedded in the post, so
this step is **optional**. A real screen recording still beats it, because it shows
the 10-second stream happening in one unbroken take rather than as a time-lapse.

**Setup, once:** `Cmd+Shift+5` → Record Selected Portion → drag the box over the
browser window. Have Terminal and Chrome side by side, terminal on the left.
Keep the clip under 70 seconds. Don't narrate while typing.

| # | Time | Do this | Say this |
|---|------|---------|----------|
| 1 | 0:00–0:10 | Terminal, visible: type `redpen` and hit return. Let the browser open. | "This is RedPen. One command, and it starts a local Gemma 3 1B model and opens the app on localhost. No account, no API key." |
| 2 | 0:10–0:22 | Drag `samples/northgate_msa.pdf` onto the drop zone. **Wait — the findings appear instantly.** Point at the gauge. | "Notice that appeared immediately. That's 65 open rules, about twenty milliseconds, no model involved. Every finding cites the clause, the page, and the exact words." |
| 3 | 0:22–0:38 | Leave it alone. Let the brief, then the explanations, then the email land on screen. | "Now the model is streaming — still on this machine. Brief first, then per-finding explanations, then the negotiation email." |
| 4 | 0:38–0:52 | Click the email, hit **COPY EMAIL**. Then click finding 1 and show the quoted clause. | "That email is genuinely sendable. And if you don't trust a finding, here's the source — click through and it's right there in the document." |
| 5 | 0:52–1:05 | Click the **fair contractor deal** chip. Score 0. | "And this is the part that matters: a fair contract comes back empty. A tool that flags everything is a tool you learn to ignore." |

**If you only record one shot:** do #2 and #3 in a single take — the instant rules,
then the model streaming behind them. That contrast *is* the product.

**Where to host it:** Loom or unlisted YouTube, then paste the link into the post's
Demo section. Don't upload the MP4 to a drive link — judges click and expect it to play.

## 3. First-user log

Fill this in as replies land, then send it to me and I'll fold it into the post's
**My first user** section. Don't publish that section with anything invented.

```
Name / handle (OK to credit?):
Trade:
Contract they ran:            signed already / about to sign
Findings they agreed with:
False positives they spotted:
Would pay $19?                yes / no / what price
What they asked for next:
Quote I can use verbatim:
Date:
```

---

## 4. Before publishing the post

- [ ] Demo link pasted into **Demo**
- [ ] **My first user** filled in, or the section deleted entirely
- [ ] Screenshots still load (they point at `raw.githubusercontent.com`)
- [ ] `python3 -m pytest -q` green (64 tests) and `-m slow` green with the model
- [ ] `./scripts/offline_proof.sh` still passes after any rule edits
- [ ] Tags include `devchallenge` and `hf26challenge`
- [ ] Published by **2026-10-18 23:59 PDT**
- [ ] Optional: claim free partner credits at hacktoberfest.com/my (Gemma needs
      none, but Tinker/Render/Backboard/ElevenLabs credits are there)
