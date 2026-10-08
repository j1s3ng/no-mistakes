# Test sanity audit

Historical snapshot at cumulative pass eighteen. The subsequent conditional
publication decision and incumbent comparison are recorded in
[the v0.4.0 release comparison](release-comparison.md).

Date: 2026-10-08. Baseline: 156 passing unit tests. Passing was the starting point,
not the acceptance criterion: three independent reviews and parent checks injected
specific faults into disposable copies or isolated processes. No live network,
user history, or publication was involved.

## A real defect, not just missing tests

The retrieval helper accepted an `Evidence` subclass, retained its dynamic class
through `replace`, and called an overridden `to_dict`. An independent fixture
emitted 26,000 characters while reporting four retained characters under a
four-character limit. It could also replace checked provenance in serialized output.

Retrieval now emits the canonical `Evidence` schema. A regression checks actual
retained text, source/scope/provider/ID, clipping provenance, and aggregate accounting.
It failed against the original behavior and passes after the repair. The test does
not prescribe whether a subclass serializer must be called; an initial assertion
about invocation strategy was removed during review. Callbacks remain trusted code;
this repair is not a sandbox or a prompt-injection defense.

## Faults that previously escaped

| Fault condition | Why earlier checks stayed green | What now detects it |
| --- | --- | --- |
| Remove final-artifact validation | One test invalidated artifact and review evidence together. | Each invalid artifact is tested with an otherwise valid report. |
| Remove review-evidence validation | The invalid artifact masked the missing second error. | Each review aspect/evidence field is invalidated independently. |
| Lose the candidate cap during external query sanitization | Cap tests were local; external-query tests used small limits. | Observe the sanitized callback request with limit ten and cap three. |
| Invoke a provider after sanitizer failure, still report blocked | `self.fail` inside the callback was swallowed by exception handling. | Record calls and assert no invocation after the helper returns. |
| Remove HTTP response cap and bounded read | Invalid JSON failed parsing even without the cap. | Valid JSON is accepted at its exact byte boundary and rejected one byte over; read size is recorded. |
| Stop wiring the no-redirect handler | The handler was tested separately from mocked request construction. | Inspect the actual handler passed to the opener. |
| Omit the HTTP timeout | Mocked transport accepted missing configuration. | Check the timeout passed to the opener. |
| Hardcode the default timeout | The first strengthened fixture still used that default. | Exercise a nondefault timeout of 1.25. |
| Read private context through `read_text` in doctor | Privacy guards intercepted only `read_bytes`. | Record standard `io.open`/`builtins.open` attempts and check forbidden paths afterward. |
| Create native adapter directories before failed preflight | Failure snapshots captured files only. | Snapshots include directories, modes, and symlink targets. |
| Discover zero tests in CI | Ordinary unittest discovery exits successfully for an empty suite. | CI rejects zero tests and all-skipped results, while allowing passing tests with some skips. |
| Omit `http_adapter.py` from an installed wheel | Source tests passed; wheel checks required only `cli.py`; installed smoke skipped retrieval. | Compare every packaged Python file to source and run installed retrieval outside the checkout. |

The ten code mutations and two CI failure fixtures above are now detected by the
revised checks. The hardcoded-timeout gap was found after the first strengthening
pass and then closed. Positive controls already caught ownership-check removal,
private `read_bytes`, and loss of inherited clipping provenance. These are selected
faults, not a comprehensive mutation score or proof that no bugs remain.

## Validation and limits

The final suite passes 159 tests. Exact CI runner fixtures reject empty, all-skipped,
failing, and import-error suites, and accept passing and mixed pass/skip suites.
A wheel missing its HTTP module now fails both archive inspection and installed
retrieval. Current unmodified distributions and installed entrypoints pass locally.

Transport tests use mocks; no real endpoint, redirect server, or external account
was exercised. In-process mutants do not alter subprocess CLI imports; source-copy
mutants and installed-wheel probes supply separate evidence. File inventories do
not prove absence of transient effects, and standard-I/O guards do not intercept
every possible syscall. At this audit snapshot, GitHub-hosted CI and the
Python-version matrix were unrun under the then-active publishing hold.
Model behavior and native skill discovery are
separate measurements. The [audit review](test-audit-review.report.json) records
actual checks, scope, and cumulative passes.
