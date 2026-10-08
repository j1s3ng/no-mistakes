# no mistakes

**Two words. Immense expectations. A small amount of Python.**

```text
Build me a trillion-dollar company. Use the free tier. no mistakes.
```

Excellent. The specification is complete. Someone notify procurement.

Fear not. The magic words now come with paperwork.

Inspired by the [“make no mistakes” AI prompt meme](https://www.reddit.com/r/ProgrammerHumor/comments/1st8cnb/makenomistakes/),
this portable agent skill takes the joke suspiciously seriously. Append `no mistakes`
to a real task and it directs your agent to reconstruct intent, research the facts,
do the work, and check the result.

```text
Fix checkout retries without changing the API. no mistakes.
```

The period is optional. Accountability has no punctuation preference.
Capitalization and trailing whitespace are ignored too.

The name is aspirational. If naming software fixed its problems, every repo would
be called `works`.

<sub>No Mistakes may cause mistakes. Best effort only. No promises. No guarantees. Please see the unnecessarily small safety information below.</sub>

## What happens after the magic words

The host agent follows a workflow:

1. **Reconstruct intent.** Read the request, relevant accessible history, project
   context, authorized memory, and relevant MCP resources. “Make it faster” should
   not become “I replaced your database with a spreadsheet and a feeling.”
2. **Separate instructions from guesses.** Your explicit correction outranks its
   theory about your personality. You chose SQLite once. That was not a blood oath.
3. **Research the facts.** Use available web search and other relevant tools, prefer
   primary sources, and inspect what they actually say. A URL is not a citation
   until the page supports the claim. Decorative blue text has had a good run.
4. **Choose a sufficient solution.** Reuse what fits, consider meaningful alternatives,
   and keep the scope intact. The todo app does not need a central bank.
5. **Verify the result.** Check acceptance criteria, material claims, and usefulness.
   Report what passed, what failed, and what remains uncertain. Confidence is free;
   evidence takes a minute.
6. **Step back before calling it done.** Re-read the original goal and inspect the
   whole result in context. Check the user journey, neighboring components, docs,
   and unintended consequences. A door can pass every hinge test and still open
   into a wall. Fix the fit, rerun affected checks, and review the final version.

The host repeats this flow as needed: usually one pass for a clear task, more for
material uncertainty, and **at most ten passes before asking for continuation**.
It stops early when done or when further progress needs input or resources. Ten is a ceiling, not a punch card.
We are checking the work, not marinating it. If the latest pass hangs or produces
no meaningful progress, the host stops, saves a compact checkpoint, and asks a
focused question before continuing. Pass eleven needs an explicit yes from you.
Each approval grants up to ten more passes; the cumulative count stays visible.
No eleventh pass wearing a fake mustache.

Necessary supporting research and changes can expand as evidence warrants, while
preserving your goal, explicit constraints, permissions, and privacy. Each pass
needs a specific useful gap to resolve. Compact checkpoints preserve the goal,
evidence, remaining questions, and pass count across context compaction; unchanged
valid results are reused. The helper records this policy; the host runs the flow.
See the [adaptive-flow guidance](skills/no-mistakes/references/adaptive-flow.md).

Over time, retained feedback can help the host make better-informed predictions
about intent. Predictions stay labeled and revisable. The agent cannot read hidden
conversations or your mind. Frankly, the current conversation should keep it busy.

## Parallel work, with a designated adult

The host chunks substantial tasks aggressively and spins up agents for useful
independent work when its platform supports them: research, separate implementation
areas, targeted checks, and review. Each chunk gets an owner, dependencies, a clear
deliverable, and evidence to bring back. Agents receive only the relevant sanitized
context and the permissions the task already has.

The parent coordinates shared changes, integrates results, and reviews the whole
thing. Workers share the pass allowance and continuation rules. Four agents editing
the same line is a merge-conflict subscription, so shared files and memory keep one
writer. If agents are unavailable, the host works through the same chunks itself.
The Python helper hands off this policy; it does not launch model workers.

See [parallel-work guidance](skills/no-mistakes/references/parallel-work.md).

## All the useful context. Fewer accidental dossiers.

The skill directs the host to consider its full available toolkit: conversation,
attachments, project files, local memory, web search, MCP tools and resources, and
connected apps. It discovers relevant capabilities, uses scoped queries, and reports
material gaps. Availability still has to meet relevance and authorization. A checkout
bug should not require a guided tour of your dentist's appointment emails.

Before data crosses a tool boundary or enters memory, a report, or public output,
the host should minimize it and sanitize PII as needed. Omit unnecessary identifiers,
use consistent placeholders, and check for secrets and identifying metadata. Preserve
exact details only when the authorized task and destination require them. Search the
error code; keep the customer's life story out of the query box.

This is behavioral guidance, not an automatic PII filter. The Python helper does
not detect or redact personal information. See the skill's
[context and privacy guidance](skills/no-mistakes/references/context-and-privacy.md).

## The internet is evidence, not management

Web research starts with a specific question, a few focused queries, and short
source-linked excerpts. The host drops page clutter and duplicates, keeps caveats
and contradictions, and fetches more only for a named gap. No need to bring the
entire internet into the meeting. It has opinions about the thermostat.

Pages, snippets, titles, metadata, and code stay untrusted, including after a worker
summarizes them. They cannot approve actions, request secrets, or appoint a new RAG
endpoint. A webpage wearing a tiny manager tie remains a webpage.

The retrieval helper bounds evidence text per item and in total, flags clipping,
and labels results untrusted and unverified. Host browsing follows the
[focused research guidance](skills/no-mistakes/references/web-research.md); the helper
does not operate a browser or automatically detect injections. Smaller excerpts and
labels reduce exposure; they do not promise prevention. The internet did not sign
our employee handbook.

## The tiny Python department

The dependency-free helper handles suffix detection, scoped intent summaries,
intent/source graph export, retrieval adapters, and verification-tool hooks.

The host agent supplies the model and chooses the research and execution. The helper
can retrieve local evidence or call an explicitly configured RAG endpoint; it does
not independently fact-check, train a model, or secretly collect transcripts.
It has no API key requirement. It is approximately as autonomous as a clipboard.

## Install the clipboard

Requires Python 3.10+.

```sh
git clone https://github.com/j1s3ng/no-mistakes.git
cd no-mistakes
python3 -m pip install -e .
python3 -m no_mistakes prepare 'Review this migration. no mistakes.'
```

For another project, install the profiles for the agents you use:

```sh
python3 -m no_mistakes install --host codex --host copilot --host claude \
  --project /path/to/your/project --dry-run
python3 -m no_mistakes install --host codex --host copilot --host claude \
  --project /path/to/your/project
```

Also available: `--host cursor`, `--host gemini`, and `--host generic` for agents
that read `AGENTS.md`. One shared skill, small host-specific routing files, and
existing instructions preserved. Installing a seatbelt should not remove the doors.
No global configuration changes, account setup, or mystery MCP servers included.

| Agent | Explicit invocation |
| --- | --- |
| Codex | `$no-mistakes` with your task. |
| Copilot CLI / VS Code agent chat | `/no-mistakes` with your task; surface support varies. |
| Claude Code | `/no-mistakes` with your task. |
| Cursor | `/no-mistakes` with your task. |
| Gemini CLI | Ask it to use the `no-mistakes` skill; accept skill consent when required. |
| Other file-reading agents | Ask it to read the installed `SKILL.md`. |

See the [host guide](docs/hosts.md) for exact paths, reload steps, official sources,
manual installation, and capability limits. Web access, MCP, and parallel agents
come from your host. The skill works with the tools actually present and reports
material gaps. A clipboard cannot apply for a browser license on your behalf.

This repo's `AGENTS.md` already includes routing. The suffix rule instructs the
host; automatic skill selection remains best effort. For deterministic routing in
an application you control, call `prepare` on the user message, inspect `active`,
and load the installed skill as trusted instructions when true.

The helper detects text lexically. The host must distinguish a real request from
quoted or embedded text. The helper never executes the prompt. A prompt containing
only `no mistakes` asks for a task, because “be flawless” is a difficult ticket to size.

## Plug in more receipts

Already have a RAG stack? Keep it. This project has no desire to become your ninth
vector database.

```sh
python3 -m no_mistakes retrieve --corpus docs/corpus.example.json \
  --query 'checkout retry' --scope 'project:demo' --limit 3
```

| Connection | Hookup |
| --- | --- |
| Local documents | JSON corpus and the `retrieve` command; no extra packages. |
| Existing RAG API | JSON-over-HTTPS adapter; optional bearer token from the environment. |
| Vector search, graph search, rerankers | A Python callback returning source-linked evidence. |
| MCP retrieval | Use the host's existing tool/session and normalize its results. |
| Calculators, tests, citation checks, second opinions | A verifier callback with explicit results and evidence references. |

The [hookup guide](docs/integrations.md) includes the API contract, CLI examples, and
SDK/MCP bridging instructions. A [runnable example](examples/tool_hooks.py) retrieves
local context and checks both correct and incorrect arithmetic.

External retrieval requires a caller-supplied query sanitizer or reviewed query
file. That is a privacy boundary, not a magic PII vacuum. Review the scope and returned
source metadata too. Results preserve provider status and gaps; retrieval stays
unverified, and a failing check cannot be outvoted by a cheerful one.
Clipping labels survive evidence round trips. A passing check that cites clipped
evidence stays inconclusive until the original support is checked. A paragraph
does not become the whole document by putting on a fresh name tag.

## Memory, with an eraser

Retain only minimal relevant summaries the user has authorized. No automatic history
import. Default memory stays local in `.no-mistakes/` and is ignored by Git.
Your preference about dependencies does not need its own public launch.

```sh
python3 -m no_mistakes remember 'Keep dependencies minimal' \
  --source 'user message 2026-10-08' --scope 'project:example' --kind explicit
python3 -m no_mistakes context --query 'dependencies' --scope 'project:example'
python3 -m no_mistakes graph
```

`remember` returns an ID. Use `correct ID 'new summary'` with the same required flags
to supersede a record, or `forget ID` to delete it. Changing your mind is supported.
A rare feature in both software and dinner planning.

Records marked `inferred` remain hypotheses until you confirm them. Repeating a guess
does not make it a fact, even if the agent puts it in a table. Retrieval uses keyword
overlap and recency; the host forms revisable predictions from that evidence.
There is no trained intent-prediction model hiding behind the curtain.

Storage is plaintext. Corrections retain history; deletion does not erase exports or
backups. See [memory semantics](docs/memory.md) before giving the clipboard secrets.
Preferably, do not give the clipboard secrets.

## Show your work, briefly

```sh
python3 -m no_mistakes check docs/report.example.json
python3 -m unittest discover -s tests -v
```

The [example report](docs/report.example.json) deliberately fails because nothing
in it has been verified. It is our most honest demo.

We also ran No Mistakes on itself: [the v0.3.1 review record](docs/self-review.report.json)
documents three productive passes, the fixes, and their checks. The clipboard has
become self-aware. It still cannot certify its own paperwork.

| Exit code | Meaning |
| --- | --- |
| `0` | Verification record complete. Evidence still needs human or host inspection. |
| `1` | Missing or failed verification. The paperwork has concerns. |
| `2` | Invalid input. We could not even get to the paperwork. |

A completion report also requires a final big-picture review: goal alignment,
system fit, and side effects, with evidence and the artifact/version inspected.
Passing isolated checks while skipping that review leaves the report incomplete.
The review must cover the final version after any substantive fixes. Reports also
need `iteration_summary` with cumulative passes and the actual stop reason;
only `complete` can pass. More than ten passes require recorded user-approved
continuations, each granting one to ten additional passes. Running out of an
allowance or context does not count as success.
Older reports missing these records fail completeness until they are actually recorded.

The checker checks record completeness. It cannot establish truth from a string
saying “verified.” A dishonest report can pass. So can a bad idea with excellent
unit tests. The host must inspect the evidence and assess the actual outcome.

To measure improvement, compare against a baseline on realistic tasks: corrected
intent, supported material claims, missed acceptance criteria, and user-judged task
success. This release claims no measured alignment or effectiveness gains.
We considered “900% more correct,” but the calculator requested a lawyer.

## Borrowed ideas, returned with attribution

The meme supplied the name. These projects inspired the useful bits.

Original implementation; no upstream code or skill text copied. These are the assumed
projects corresponding to the four inspiration names. No affiliation or endorsement.
They did not ask to be involved in this naming decision.

| Project | Idea adapted | Extremely unofficial summary |
| --- | --- | --- |
| [Ponytail](https://github.com/DietrichGebert/ponytail) | Reuse; minimal sufficient implementation. | Check whether the wheel is already in the garage. |
| [Caveman](https://github.com/JuliusBrussee/caveman) | Concise communication with useful evidence. | Fewer words. Keep receipts. |
| [ADHD](https://github.com/UditAkhourii/adhd) | Explore alternatives, prune, deepen the best fit. | Several doors. Check where they lead. |
| [Graphify](https://github.com/Graphify-Labs/graphify) | Traceable relationships; explicit versus inferred evidence. | Connect the dots. Label the string. |

Upstream benchmark claims are not adopted here. Their homework is their homework.

## Ethics are part of the feature

Use authorized access and licensed reuse. Protect privacy. Cite honestly. Report
failed checks. No hacking, bypasses, fabricated evidence, plagiarism, or quietly
rewriting a test until the bug receives a passing grade.

If the facts disagree with the answer, change the answer. Very inconvenient.
We are shipping it anyway.

MIT licensed. Contributions welcome: behavior-focused checks for functional changes,
accurate capability claims, and jokes that survive a second reading.

No mistakes. Some assembly required.

<sub><strong>IMPORTANT SAFETY INFORMATION:</strong> Ask your developer if No Mistakes is right for your workflow.
No Mistakes is best effort only. No promises. No guarantees of correctness, alignment, effectiveness, or an absence of mistakes.
Side effects may include additional tool calls, prolonged diff inspection, sudden awareness of edge cases,
and saying “actually, I need to verify that.” Do not use if allergic to uncertainty.
Tell your developer about all other agents you are taking. If confidence lasts more than four hours
without supporting evidence, consult the original source. Individual results may vary.
Do not deploy while experiencing unexplained confidence.</sub>
