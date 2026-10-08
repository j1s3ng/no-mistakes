# v0.6.0 MCP setup workflow review

The v0.5.0 toolbox could create a reviewed native configuration, but left the
operator to discover how to install/connect, inspect real tools, and prove useful
behavior. This update adds a concrete handoff without another package installer.

## What changed

- `toolbox setup PLAN` generates digest-bound, inert installation/connection,
  authentication, smoke, task-use, big-picture review and removal instructions.
- `toolbox doctor PLAN` observes exact native config bytes, executable presence and
  named credentials in the helper environment. It never runs commands or contacts
  services. Runtime versions, host environment, authentication, browser binaries,
  advertised tools and successful behavior remain unverified.
- Host-specific steps use primary owner documentation. A local Playwright fixture
  has an observable click result; connection/navigation alone is insufficient.
  The pinned browser installer is a separately approved repair that can affect the
  system browser, not an automatic fallback.
- GitHub's curated recipe uses a named PAT reference with its existing read-only
  headers. Cursor gets explicit transport types. Existing user configurations are
  never silently rewritten; old Cursor proposals may need rebuilding/review.
- Proposal reads reject symlinks, special files and a file replaced during opening. Config
  reads also reject special-file replacements without hanging before approval.

## Evidence

Local validation used Python **3.11.6**:

- **251 tests passed**, including **53 new tests** for setup, readiness, document
  reading and recipe repairs.
- All **198 untouched v0.5.0 tests** passed on the incumbent, and again with the
  candidate implementation substituted. The regression ruler was not rewritten.
- Independent isolated fault checks detected bypassed proposal validation,
  inherited browser commands for a different custom recipe, invented HTTP local
  launches, a false runtime-available claim, and weakened explicit-approval guidance.
  The last check validates generated guidance, not an independent consent mechanism.
- Real FIFO tests run in bounded subprocesses, including replacement between the
  initial path inspection and opening the descriptor. Private config/environment
  canaries stay out of diagnostic output. Side-effect traps cover execution,
  network calls and writes in the new inert/read-only paths.
- Skill validation and whitespace checks passed.
- Wheel and source distributions built successfully. Their helper/skill/source
  payloads were compared with the checkout; the source includes the HTML fixture.
  The wheel has no runtime dependencies. Prior installed-CLI checks and the new
  setup/doctor flow passed from a disposable environment outside the checkout.
- Four fixed CLI cases improved over the original v0.5.0: setup instructions,
  missing-config diagnostics, exact-config diagnostics with runtime still
  unverified, and rejection of a FIFO document. The incumbent lacked the two new
  commands and stalled until a two-second subprocess timeout on the FIFO;
  the candidate returned the intended results. This measures helper behavior,
  not a model's general accuracy or alignment.

CI also exercises the installed setup/doctor path outside the checkout using an isolated
synthetic HTTP configuration; no host loads it and no provider is contacted.

## Limits and overall fit

No third-party MCP was downloaded, installed, launched, connected, authenticated
or behavior-tested for this change. Host instructions and package source were
inspected; they are not evidence of a working integration in every client. The
browser fixture was added, but its real MCP smoke must be run after the user
approves that connection. Installed-wheel users use their own known local page;
the example fixture is included in the source distribution.

`local_ready` means only that the limited local checklist passes. A valid merged
configuration can remain a manual-review finding because the helper compares
exact bytes. A desktop host may have different environment variables. Named
credentials are references, not a general PII sanitizer. Scope prose is not an ACL.
Remote services and research can change; recipe freshness is still enforced.

The package remains a dependency-free workflow helper and skill, not a model
runner, MCP server bundle, independent fact checker or guarantee of correctness.
Actual task evidence and the final big-picture review remain the host agent's work.
