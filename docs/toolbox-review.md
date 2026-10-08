# v0.5.0 toolbox review

Date: 2026-10-08. Baseline: v0.4.0 at
`9a36838c3d4413dfa53fec921501375ca5bd247e`.

The new request was a broad practical toolkit plus researched, user-approved MCP
additions. Acceptance: capability profiles that prefer existing tools; curated
recipes and custom dossiers; reviewable host-specific configuration; an explicit
decision before native writes; preserved user configuration; truthful packaging
and verification. The candidate adds this workflow, which the incumbent did not
provide. This is feature coverage and tested compatibility, not a model-accuracy
or performance benchmark.

## Evidence and fixes

- Final candidate suite: **198 tests passed**, including 39 toolbox tests.
- Exact incumbent archive: **159 tests passed**. Only its `no_mistakes` package
  was replaced for a second run: the same **159 untouched tests passed** on final
  candidate code. Its tests, corpus/docs and skills remained incumbent bytes.
- Independent temporary-copy fault checks rejected removed confirmation gating,
  plain `yes` acceptance, disabled canonical tamper checking and missing initial
  destination preflight. These are selected faults, not an exhaustive mutation score.
- Independent review found an actual gap despite 38 green toolbox tests: a dossier
  could state version `9.9.9` while its npx command pinned `0.0.83`. The parent
  reproduced it. Each npx recipe now requires one exact package pin equal to the
  reviewed version. A CLI regression rejects the mismatch without writing files.
- Planning all five curated tools across six native selectors and generic used
  synthetic projects, left them unchanged, and leaked no injected environment
  canary. Native apply created only selected temporary targets; generic stayed inert.
  Network/execution interception observed no calls in that scoped probe; this is not
  monitoring of every syscall or proof about code executed by a host later.
- Final source/wheel build and byte comparisons passed. Installed entrypoints ran
  in a separate environment outside checkout. Real installed plan/show commands
  were inert; piped apply was blocked. A synthetic PTY confirmation created exactly
  the selected temporary config. No MCP host or third-party server was launched.
- Installed regression checks passed for retrieval, canonical provenance/bounds,
  required verifier coverage, summaries, memory/deletion semantics, six skill host
  profiles, dry-run, repeat idempotence and read-only/aggregate diagnostics.
  The wheel contains eight canonical Markdown skill files with eleven checked
  installed relative links. Python runtime dependencies remain empty.

## Review the finished whole

**Goal alignment:** profiles cover common coding, web, research, data, documents,
knowledge, ops and design tasks. They are hypotheses about needs, not inferred
permission. Five optional researched MCP recipes and custom dossiers support a
small relevant selection; no automatic all-tools startup or credential collection.

**System fit:** reviewed actual CLI commands, native transport/env syntax, source
package contents, installed entrypoints, conditional skill routing and docs together.
Copilot CLI and VS Code are separate selectors. Normal skill installation still
only installs instructions. Existing native MCP configs require reviewed manual
merging; native apply currently requires POSIX, while rendering remains portable.

**Side effects:** plan/show never install, authenticate, connect or execute. Apply
preflights before prompting, rejects conflicting existing files, rechecks after
confirmation, refuses symlinks and places a new mode-0600 file without overwriting.
A native host can execute packages or contact services when it loads that file,
which is why the user's approval precedes creation. Requested scope and digest are
not a sandbox, account ACL, proof of research or cryptographic identity service.
Provider/process permissions and host approval controls remain necessary.

The third-party recipes were researched from primary owner documentation and tagged
release metadata; none was installed, authenticated or behavior-tested. Custom
dossier truth must be inspected by the host/user. Thirty-day freshness checks do
not turn a recent timestamp into verified research. Native host discovery and model
effectiveness remain unmeasured. GitHub's Python 3.10/3.13 run occurs after this
prepublication snapshot and belongs to the published commit.

Decision: retain the feature after these bounded checks and publish under the
existing conditional authorization. Third-party MCP connections remain separately
user-approved. Best effort only; no promises or guarantees.
