# v0.4.0 versus the incumbent

Date: 2026-10-08. Incumbent: public `main` at
`22bb044f683006ae729740e47e50ad79619b2068`, version 0.3.1.
Candidate: 0.4.0, with implementation hashes in the
[comparison observations](release-comparison.results.json).

The user authorized publication if the candidate demonstrated an improvement.
Acceptance was fixed before inspecting outcomes: concrete shared-API improvements,
no worse fixed controls, untouched incumbent tests passing on candidate code,
candidate tests, real installation upgrades, and final distribution checks.
The [release review](release-review.report.json) records the decision and cumulative
passes. Earlier publishing holds remain historical facts in their review snapshots.

## Observed comparison

One unchanged synthetic probe file ran in separate processes against the exact
incumbent archive and a candidate source snapshot. It used only shared signatures;
the new `required_verifiers` and `budget` keywords were excluded from paired
criteria. Additive output telemetry was allowed equally in the shared-field checks.

| Check | Incumbent | Candidate |
| --- | --- | --- |
| Evidence subclass overrides output | 10,000 returned text characters despite a reported 12-character retention limit; altered provenance | 12 characters, original checked provenance, canonical fields |
| Four malformed present correction relationships | Self-reference, cross-scope, nonreciprocal link, and cycle accepted; mutation wrote the store | Each rejected before writes |
| Verifier subclass overrides checked failure | Serialized result and aggregate verdict became `passed` | Checked `failed` verdict preserved |
| Five 6,000-character verifier summaries | 30,000 retained characters | 8,000 retained characters; verdict and references preserved |
| Other shared-API controls | 23 satisfied | The same 23 satisfied |
| Untouched incumbent tests | 115 passed | 115 passed with candidate implementation overlay |

There were seven improved criteria, 23 satisfied ties, and zero observed regressions
in these 30 checks. These counts describe selected deterministic cases, not a
statistical accuracy score. Six improvements repair validation or serialization;
the seventh exercises a new diagnostic-retention default through the common API.
The incumbent did not promise that new capacity bound.

For the compatibility run, only the incumbent's `no_mistakes` directory was replaced.
Its tests, docs/corpus, and skill files stayed byte-identical. The separate candidate
suite passes 159 tests. The earlier [test sanity audit](test-audit.md) also shows
which deliberately broken implementations the strengthened checks detect.

## Installation upgrade and release checks

Real CLI subprocesses installed 0.3.1, then upgraded the same synthetic projects to
0.4.0: each of six host profiles and an all-host project. Candidate payload bytes
matched exactly. Custom instructions, unrelated settings, synthetic private memory,
unowned files, and modes were preserved. Dry-run and doctor were read-only;
repeated installation reported every file unchanged.

Five malformed-manifest, malformed-routing, or locally edited owned-file cases
exited 2 without persistent writes. Subset upgrades preserved unselected routes,
adapters, and ownership, including a locally customized unselected Claude command.
A clean synthetic retired owned reference was deleted; an edited one blocked the
upgrade. Normal upgrades changed only skill payload and manifest: routing/adapters
already matched the candidate. These are file-contract checks, not native host
activation measurements.

Source and wheel checks compare packaged files to final source bytes, exclude
private/cache files, and exercise installed entrypoints outside the checkout.
Runtime dependencies remain empty. Local checks use Python 3.11; GitHub Actions
executes the Python 3.10/3.13 matrix after publication. Its public run belongs to
the resulting commit, rather than being invented in this prepublication snapshot.

## Intentional changes and limits

Verifier defaults now allow at most 50 checkers, 50 references per result,
1,024 characters per metadata field, 2,000 characters per summary, and 8,000 summary
characters in total. Over-capacity checker input is rejected before callbacks;
summaries are clipped with telemetry. Configure `VerificationBudget` for a different
supported workload; see [integrations](integrations.md#bound-returned-checker-diagnostics).
These defaults change behavior for callers exceeding them. The evidence does not
establish blanket backward compatibility. Inconsistent present memory relationships
are also deliberately rejected; deleted-history references remain supported.

Callbacks are trusted executable code. Canonical serialization and retained-text
limits do not sandbox them, limit their allocations/runtime, redact all PII, or
prove injection resistance. Network transport tests use mocks. No real HTTP service
or account was exercised. File inventories establish persistent observed state,
not absence of every transient effect or syscall.

Model effectiveness, intent prediction, and native host discovery still lack a
matched measurement. Earlier inconclusive and unrun behavior observations remain
in the historical reports. Best effort only. No promises. No guarantees.

## Reproduce the paired helper checks

From a trusted candidate checkout, create an incumbent snapshot outside it:

```sh
mkdir /tmp/no-mistakes-incumbent
git archive 22bb044f683006ae729740e47e50ad79619b2068 | tar -x -C /tmp/no-mistakes-incumbent
python3 examples/compare_snapshot.py /tmp/no-mistakes-incumbent /tmp/incumbent-observations.json
python3 examples/compare_snapshot.py . /tmp/candidate-observations.json
```

Use fresh output paths: the script refuses to replace an existing file. Omit the
output argument to allocate a new temporary directory. The script imports code
from the explicitly selected trusted snapshot, checks module origins, uses only
synthetic temporary fixtures and local callbacks, and records observed outcomes.
It does not fetch revisions, invoke a model, or turn criterion counts into a quality
score. Compare matching `name` and `expected` fields from the same script hash;
`satisfied` changing from false to true is a repaired case, true to false a regression.
