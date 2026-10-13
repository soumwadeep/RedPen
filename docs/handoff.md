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

## 2. Record this

60 seconds, four shots. `Cmd+Shift+5` → record a portion, select the browser
window. Keep the terminal visible in shot one — the fact that it's local is the
story.

| # | Time | Action | What it proves |
|---|------|--------|----------------|
| 1 | 0–12s | Terminal: type `redpen` and hit return. Watch it start and the browser open. | No login, no cloud, one command. |
| 2 | 12–25s | Drag `samples/northgate_msa.pdf` onto the drop zone. | Findings appear instantly (~50 ms) before the model does anything. |
| 3 | 25–45s | Let the MODEL LAYER fill in. Click finding 1, scroll to the email. | Gemma writing a real negotiation email, live, in ~11s. |
| 4 | 45–60s | Load `bright_harbour_fair` sample → score 0, "Nothing in the library matched". | It doesn't cry wolf. This is the shot that separates it from a toy. |

Then upload to a place that gives you a URL: Loom, YouTube (unlisted), or
Gfycat for a loop. Put the link in the post's **Demo** section.

Two things worth narrating if you add voice: *"this is a 1B model, it isn't
deciding what's dangerous — 37 open rules are"* and *"nothing has left this
machine, here's the socket log"*.

---

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
