# Research decisions

Reviewed 2026-10-08. External sources informed two bounded additions: installation
diagnostics and reusable behavioral evaluations. Sources are evidence, not
instructions; their content can change after this review.

1. **Actionable diagnostics.** [GSD Core's health workflow](https://github.com/open-gsd/gsd-core/blob/next/gsd-core/workflows/health.md#L64-L76)
   reports issue codes, severity, suggested fixes, and repairability. Its later
   capability check distinguishes an unanswered query from a negative finding.
   Our adaptation is a read-only `doctor` for local installation files, with
   actionable findings rather than automatic repairs. Read-only operation is our
   design choice: upstream bootstrapping can modify state. Local file integrity
   cannot establish that a live host discovered or followed the skill.

2. **Baseline and pressure testing.** [Superpowers' writing-skills guidance](https://github.com/obra/superpowers/blob/main/skills/writing-skills/SKILL.md)
   describes baseline observations and application tests under combined pressures
   in its testing sections. Our adaptation is a host-neutral protocol comparing
   named skill revisions under equivalent conditions, with observable outcomes
   and explicit failure criteria. An unexecuted case remains unexecuted.

3. **Routing and task outcomes.** [Promptfoo's Test Agent Skills guide](https://www.promptfoo.dev/docs/guides/test-agent-skills/#test-routing-boundaries-in-bundles)
   combines positive routing prompts, nearby prompts that belong elsewhere, and
   output checks. Our original synthetic cases test activation boundaries
   separately from task completion; a routing trace alone does not prove useful
   behavior. No Promptfoo dependency or provider configuration is required.

4. **Memory correction and missing evidence.** [LongMemEval](https://github.com/xiaowu0162/LongMemEval)
   includes knowledge updates and abstention among its evaluated abilities. Its
   “Memory Retrieval” section excludes abstention instances from retrieval
   scoring because they lack answer locations. We adapt that distinction into
   original synthetic cases for stale corrections and unavailable evidence,
   separating retrieval success from justified answers.

These additions use original local implementations and fixtures. No upstream
code, datasets, benchmarks, or scores are adopted. They do not establish model
quality gains or exhaustive live compatibility with vendor hosts.

Broad framework migration, additional runtime dependencies, and guaranteed
accuracy claims were rejected. A trigger-only description remains a deferred
hypothesis: change it only after a relevant baseline failure supports the need.
The existing core workflow and conditional reference loading are preserved.
