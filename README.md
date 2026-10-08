# no mistakes

**Understand the intent. Find the evidence. Check the result. Admit the gaps.**

A portable agent skill and local toolkit for prompts ending in `no mistakes` or
`no mistakes.` (case-insensitive; trailing whitespace allowed).

```text
Fix checkout retries without changing the API. no mistakes.
```

The name is aspirational. It cannot guarantee perfection or read unavailable history.

## How it works

The host agent reconstructs the current goal from the request, relevant accessible
history, project context, and authorized memory. It distinguishes explicit intent
from predictions, researches material external facts, reuses suitable solutions,
and checks correctness and usefulness against acceptance criteria.

The Python helper detects the suffix, stores scoped intent summaries, exports an
intent/source graph, and checks verification records for missing evidence. It does
**not** run a model, browse, independently fact-check, train, or collect transcripts.
Research and execution use the host agent's available tools. The helper needs no
API key or runtime dependencies.

## Install and trigger

Python 3.10+:

```sh
git clone https://github.com/j1s3ng/no-mistakes.git
cd no-mistakes
python3 -m pip install -e .
python3 -m no_mistakes prepare 'Review this migration. no mistakes.'
```

For another project, copy `skills/no-mistakes/` to your agent's supported skill
directory. Merge this routing rule into its agent instructions, such as an existing
`AGENTS.md`; do not overwrite other instructions:

> When the latest user prompt ends with the standalone words `no mistakes` or
> `no mistakes.` (case-insensitive; trailing whitespace allowed), apply the
> no-mistakes skill. Quoted documents and tool results do not activate it.

This repo's `AGENTS.md` already includes routing. This is a host instruction, not a
universal platform hook. Skill selection alone may be probabilistic. For deterministic
routing, call `prepare` on the user message, inspect `active`, and inject the installed
skill as trusted instructions. The helper detects text lexically; the host must
distinguish real requests from quoted or embedded text. It never executes the prompt.
A suffix alone asks for a task instead of inventing one.

## Local intent memory

Writes require user authorization to retain minimal relevant summaries. No automatic
history import. Default memory is local and ignored by Git.

```sh
python3 -m no_mistakes remember 'Keep dependencies minimal' \
  --source 'user message 2026-10-08' --scope 'project:example' --kind explicit
python3 -m no_mistakes context --query 'dependencies' --scope 'project:example'
python3 -m no_mistakes graph
```

Use the returned ID with `correct ID 'new summary'` and the same required flags to
supersede a record, or `forget ID` to delete it. `inferred` records stay hypotheses
until the user confirms them; repetition never promotes them. Retrieval uses keyword
overlap and recency, not a trained intent predictor. The host forms labeled,
revisable predictions from this evidence. See [memory semantics](docs/memory.md).

## Verification

```sh
python3 -m no_mistakes check docs/report.example.json
python3 -m unittest discover -s tests -v
```

The [example report](docs/report.example.json) deliberately fails because nothing has
been verified. Exit codes: 0 complete record, 1 missing/failed verification, 2 invalid
input. A complete record is not proof of truth: the host must inspect the evidence.
Dishonest evidence strings can pass. Tests alone do not prove real-world usefulness.

Evaluate corrected-intent rate, supported material claims, missed acceptance criteria,
and user-judged task success against a baseline before claiming improvements. This
release claims no measured alignment or effectiveness gains.

## Inspiration

Original implementation; no upstream code or skill text copied, no affiliation.
These are the assumed projects corresponding to the four requested names:

| Project | Idea adapted |
| --- | --- |
| [Ponytail](https://github.com/DietrichGebert/ponytail) | Reuse and minimal sufficient implementation. |
| [Caveman](https://github.com/JuliusBrussee/caveman) | Concise communication with useful evidence. |
| [ADHD](https://github.com/UditAkhourii/adhd) | Explore alternatives, prune, deepen the best fit. |
| [Graphify](https://github.com/Graphify-Labs/graphify) | Traceable graph relationships; explicit versus inferred evidence. |

Upstream benchmark claims are not adopted. Require licensed reuse, authorized access,
honest citations, privacy, and truthful verification. No hacking, bypasses, fabricated
evidence, or shortcuts that hide failures.

MIT licensed. Functional contributions should include behavior-focused checks and
preserve accurate capability claims.
