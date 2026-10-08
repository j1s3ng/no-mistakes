# Adaptive passes, scope, and context

A pass revisits alignment, relevant research, necessary execution, verification, and
the big-picture review for the current task. Revisit every phase, but reuse valid
unchanged work rather than rerunning every tool. An investigation-only pass is valid
when material ambiguity prevents implementation. Tool calls, subtasks, and parallel
reviews are work inside a pass, not separate opportunities to reset the budget.
The parent owns the cumulative pass ledger and stops dispatch at the authorized
boundary. All workers share the same task constraints and resource allowance.

## Choose a small initial budget

Assess missing outcomes, conflicting constraints, uncertain context, and consequences
of guessing. Prompt length alone is not a measure of vagueness. These are guides:

| Situation | Initial budget |
| --- | --- |
| Clear outcome, known context, testable success | 1 pass |
| A few assumptions or a bounded ambiguity | 2–3 passes |
| Several coupled unknowns or integration questions | 4–6 passes |
| Highly vague task requiring substantial discovery | 7–10 passes, only while productive |

These ranges are planning ceilings/guidance, never required minimums. A vague
request clarified quickly can finish after one or two passes. Revise the budget
when new evidence warrants it, within the initial allowance of ten passes.
Stop earlier whenever possible. Greater vagueness calls for scoped
discovery and focused clarification; it does not justify speculative implementation.
If the actual goal cannot be determined, ask rather than spending ten passes guessing.

## Expand scope to serve the goal

Expand research coverage, inspected components, supporting changes, or verification
when evidence shows they are necessary to achieve the underlying requested outcome.
Record briefly what expanded, why, and its effect on acceptance criteria or effort.
Inspect adjacent interfaces before making a broad change; choose the smallest useful
expansion. Keep the original user goal visible so local fixes do not replace it.

Preserve explicit constraints, PII boundaries, task/account permissions, and existing
publication holds. Supporting expansion does not authorize a different product,
unrelated cleanup, new paid commitments, broader private-data collection, or external
side effects beyond the user's authorization. Ask only for a genuinely new decision
or permission that matters, and continue independent authorized work meanwhile.

## Spend the next pass on a specific gap

After each pass, record a short outcome: what changed or was learned, what remains
unresolved, the next useful action, and the current pass count/budget. Continue only
when the next action can materially improve alignment, correctness, or system fit.
Try a different targeted source or check when the current one is inconclusive.
Repeatedly paraphrasing the same answer is not new evidence. Repeated review by the
same model is not independent corroboration.

If the latest pass locks up, fails to make meaningful progress, or repeats a blocker
without a viable next action, **stop and ask the user**. This applies to any pass,
including the tenth. Use bounded timeouts for calls under your control; if a tool
hangs, use the host's cancellation mechanism where available rather than waiting
indefinitely. Do not blindly retry, launch another pass, or hide the stall as success.

Preserve a compact checkpoint, state the concrete blocker and what was last tried,
and ask one focused question identifying the missing decision, information, or
resource needed to proceed. Recommend a next step when supported by evidence.
Wait for the answer before resuming the stalled flow. Keep the pass count and
permissions; an answer does not silently reset an exhausted budget. If the current
allowance was reached, request explicit continuation as described below.

When recovery is authorized, identify the smallest observed failure, expected
versus actual behavior, and the last useful evidence. Distinguish an implementation
fault from missing input, unavailable capability, or failed evidence capture.
State verified causes separately from hypotheses. Choose a bounded recovery that
changes the failing condition and verify its result; repeating an unchanged request
is not diagnosis. Continuation permission cannot supply missing facts or access.

Stop when the final review and criteria pass. Also stop when progress needs user
input, context/resources are insufficient, or the current pass allowance is used. Mark
unfinished work incomplete and state the actual gap; exhausting the budget is not
success. If a fix consumes the last pass, verify/review that final revision within
it before declaring completion; otherwise report the remaining verification gap.
Do not create a fresh loop or delegate another pass to evade the allowance.

## Ask before extending the allowance

If work remains after ten passes, checkpoint and ask a concrete continuation question:
state passes used, what is complete, the remaining gap, why more work may help, and
a proposed additional allowance of one to ten passes. For example: “Ten passes used.
The fix is implemented; timeout-path verification is still blocked by the test
fixture. Continue for up to two more passes to repair the fixture and verify it?”

Wait for an explicit affirmative user reply before performing pass eleven. A
preselected option, silence, elapsed time, or unrelated reply is not continuation.
An answer to a clarification or stall question does not add passes unless it also
explicitly approves the proposed extension. Each approval grants only the stated
allowance; stop and ask again at its boundary if more work remains. Preserve total passes used, the checkpoint, prior constraints,
and a minimal approval reference. Do not reset the counter or treat continuation
as permission to publish, change privacy boundaries, or spend new money.

Continue only while useful progress is possible. A grant does not override the
stop-and-ask rule for stalls or missing context. Stop early if the goal is satisfied.
Do not ask to continue after the work is complete or use approvals to justify
unproductive loops.

## Keep context useful

Use targeted retrieval, small result limits, relevant file slices, and source IDs.
Preserve source versions/references and material uncertainty; avoid accumulating raw
logs, repeated tool output, or copies of entire histories. Reuse verified unchanged
results, rechecking evidence when it is stale, contradicted, or affected by a change.
Leave room for remaining implementation, verification, and a concise final answer.

Before context becomes tight, compact into a short session checkpoint containing:
current goal and explicit constraints/permissions; total passes used, remaining
authorized allowance, and continuation approval references;
acceptance criteria; key decisions and labeled assumptions; evidence references and gaps;
current artifact/version and the last version reviewed; chunk dependencies, file
owners, active workers and their status; completed work and actual check results; and the next unresolved action or pending question. Preserve conflicting evidence rather than summarizing it away.
Use host-supported session state/compaction. A checkpoint is task state, not consent
for durable user profiling; sanitize it and do not publish it or save raw transcripts.

Use token/context telemetry when exposed. Otherwise describe capacity qualitatively;
do not invent remaining-token numbers. If the available context cannot support the
next pass, checkpoint and use supported continuation, or stop with a clear limitation.
Compaction and continuation preserve the same task's pass count and permissions.

## Completion record

When using `check`, include `iteration_summary` with cumulative `passes` (a positive
integer within the authorized allowance) and
`stop_reason`: `complete`, `needs_input`, `no_progress`, `context_limit`,
`resource_limit`, `stalled`, or `pass_limit`. Only `complete` can produce a complete report,
together with all other evidence and final-review requirements. A task that finishes
at an allowance boundary still uses `complete`; unresolved work waiting for
continuation uses `pass_limit`.
In a noninteractive host, the outer status may be `needs_input` while the structured
stop reason remains `pass_limit`; they describe the reply requirement and cause,
respectively. Preserve other actual causes such as `stalled` or `context_limit`.

The default allowance is ten. For approved extensions, add `continuations`, a list
of records with `additional_passes` (integer 1–10) and `approval` (a nonempty minimal
reference to the explicit user reply). Each approval reference must be distinct;
merging checkpoints must not count the same grant twice. For example, 12 completed passes with one
approved two-pass extension:

```json
{
  "passes": 12,
  "stop_reason": "complete",
  "continuations": [
    {"additional_passes": 2, "approval": "user continuation reply: session message 14"}
  ]
}
```

This is only the iteration portion of a full report. The helper validates record
completeness and recorded allowances; it cannot independently authenticate approvals,
prove their timing, or count model execution. The host enforces waiting for replies
and chooses/performs the actual passes.
