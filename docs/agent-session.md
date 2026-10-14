# Agent session log

RedPen was built agent-assisted: an AI agent wrote the code, a human owned the
claims. This is the verifiable version of "show your work" — every line here
maps to a commit in this repository, so you can check it rather than take my
word for it.

For the full interactive transcript, see the DEV agent session linked in the
submission post (if published).

## Milestones

| # | Commit | What happened |
| --- | --- | --- |
| 1 | `900b703` | Repo created, MIT licence |
| 2 | `03ff7a8` | Deterministic core: clause ingest + 37-rule library, negation-aware matching, verbatim evidence |
| 3 | `7930964` | Local app: CLI, loopback FastAPI server, UI, SSE model streaming |
| 4 | `589f146` | Guard-rails hardened; model-independence proven by swapping Gemma for Qwen |
| 5 | `7317bd5`–`2654c23` | README, screenshots, first draft of the submission post |
| 6 | `5f1d092` | Handoff kit: outreach message, recording script, first-user log |
| 7 | `f90d8f4` | Latency claims replaced with measured values |
| 8 | `7db9788` | Six real documents fed in: document typing, blanks detection, +28 rules |
| 9 | `e805921`–`ad8f842` | Post rewritten around the real-world test |

## Verified before building on it

The first thing done was not code. It was checking whether an open-weight model
runs at all on the available hardware, because the entire architecture depends
on the answer:

- 8 GB RAM, Apple Silicon, no GPU, no Docker, no cloud credentials
- `llama.cpp` present, **zero model weights on disk**
- Gemma 3 1B Q4_K_M probed for whether it downloads without an HF token
  (Gemma weights are licence-gated — the featured category was not assumed)
- Loaded in 2.3 s, 0.83 GB resident, ~110 tokens in 2.8 s
- Only then was the product designed around it

## Where the agent was wrong

Worth listing, because "the agent wrote it" is only useful if the failure modes
are on the table. Every one of these was introduced during this session:

| Defect | How it was caught |
| --- | --- |
| Every API request returned 500 while all 20 unit tests passed | A test for the HTTP surface, which the unit tests never reached |
| Uploads parsed PDFs as plain text, producing 154 garbage clauses | Test asserting page count ≥ 2 on an upload |
| Offline proof script "passed" while observing zero sockets | Reading its own output — the empty list was the tell |
| Email labelled `"gemma"` while Qwen was writing it | Model-swap experiment |
| Negotial validator rejected good output for using bullets | Real model output vs a hard-coded format assumption |
| Signature left signed "Max" | Real model output |
| Latency claimed as "~50 ms" without measuring | Measured it: 12–28 ms |
| Fee-context regex matched empty, blanking the FIGURES panel | Screenshot of the running app |
| Text before the first numbered clause silently discarded | Running a real offer letter through it |
| Unanchored `no` matched inside `not`, false-flagging a sane expense clause | Running a real freelance agreement through it |

Nine of the ten were found by tests or by looking at the running program. The
tenth was found by a human reading output that looked too good.

## What the human owned

- The architecture decision: rules judge, the model writes. Not the agent's call.
- Refusing a hosted version, after the cost and privacy math.
- Declining to publish an invented first-user testimonial, which is why
  `My First User` is absent from the submission post rather than populated.
- Every number in the post, README and this log: measured, or deleted.

## Reproduce it

```bash
git clone https://github.com/soumwadeep/RedPen.git && cd RedPen
python3 -m pytest -q                     # 98 tests, no model needed
python3 -m pytest -q -m slow             # adds a real local-model pass
./scripts/offline_proof.sh               # samples every socket during a review
redpen doctor                            # engine, weights, RAM, rule count
redpen rules --list                      # the 65-rule library
```

## Current state

- 65 rules: 19 freelance-scoped, 18 employment, 10 NDA, 18 universal
- 5,121 lines of Python, 572 lines of UI
- 98 tests
- Recall: 36 findings on a hostile MSA, 19 on an internship offer letter,
  11 on a one-way NDA
- Precision: 0 findings on a fair contract
- Model swap: identical findings under Gemma 3 1B and Qwen 2.5 1.5B
