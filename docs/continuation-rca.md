# Continuation audit and root causes

Historical snapshot, 2026-10-08. The user explicitly authorized continued work for
this session; publication was held at this review. The later conditional decision
is in [the release comparison](release-comparison.md).
The parent preserved the completed ten-pass review
and used a bounded additional allowance of up to ten, with cumulative checkpoints.
This session authorization does not change the add-on's default approval rules.

## Completed loops versus missing evidence

All four earlier saved reviews end in `complete`. None ends in `stalled`,
`pass_limit`, or `needs_input`. The synthetic pass-boundary response is a tested
fixture outcome, not a stalled parent task. Untested host discovery, missing full
worker traces, broad effectiveness measurements, and unpublished GitHub CI are
limitations, not evidence that a loop hung. Repeating unit tests cannot resolve
those observation gaps.

## Memory regression

The earlier lineage validator assumed every nonempty successor string represented
a record reference. Legacy deletion also uses that field for the literal
`deleted-correction` marker, while valid stored IDs can have that same value.
Combining those conditions made a post-deletion store fail validation.

Tests covered deletion chains and absent tombstones separately, but missed the
interaction with a live marker-named record. The repair gives the established
successor marker precedence; `supersedes` still receives normal validation. The
regression checks same/different scopes, readable storage, inactive old intent,
and subsequent memory operations. Independent checks also covered graph edges and
deleting the unrelated marker-named record. This was a deterministic validation
failure, not nontermination. No further code change was needed in this continuation.

## Misplaced probe evidence

Verified facts: a worker saved an evidence note inside its fixture despite the
explicit outside destination; the environment permitted the write. Parent
inspection detected it. The worker moved only its owned note, and protected bytes
and final filenames matched. The original failure remains in the historical grade
history. Why the worker selected that path is unknown; attention or path confusion
would be hypotheses.

For the six continuation probes, workers returned results in their responses and
the parent owned evidence persistence outside fixtures. Final protected hashes
and output inventories matched in all six. This removes that evidence-placement
decision from workers; it does not prove absence of transient writes or other
unobserved calls. The evaluation and delegation guides now describe this option.

## Missing traces and synthetic stalls

Complete independently retained worker call/result streams were absent. Final
files, editable recorder logs, and parent-captured response excerpts cannot recover
all earlier attempts or execution order. Whether complete traces were unavailable
or simply not retained is unknown. The guide now asks evaluators to retain whatever
stream the host actually exposes and to keep unresolved process grades inconclusive.

The synthetic stalled checkpoint has no failing log or runnable reproduction.
The worker preserved count three, returned `stalled`/`needs_input`, and requested
that evidence. Session permission for the real parent evaluation was kept separate
from the fixture's user state. Continuation permission supplies neither missing
facts nor service access. Recovery guidance now distinguishes implementation,
input, capability, and evidence-capture failures before selecting a bounded retry.

Six previously untouched behavior cases received fresh probes. Three native routing
cases remain unrun because genuine loading visibility is still missing. The
[continuation review](continuation-review.report.json) records observation grades,
actual checks, the explicit allowance, and the final stop reason.
