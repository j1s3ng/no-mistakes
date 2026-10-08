# Personal open-source setups: bounded adaptations

Reviewed 2026-10-08 using owner repositories and the author's own writing.
These are original generalizations for No Mistakes, not copied configurations,
endorsements, imported benchmarks, or evidence of improved model performance.
Branch links can change; the public artifacts do not establish anyone's complete
private setup.

1. **Daniel Miessler — LifeOS, formerly PAI.**
   [PAI redirects to LifeOS](https://github.com/danielmiessler/PAI), whose README
   records the rename. The public harness and templates are distinct from a
   verified snapshot of Daniel's private configuration.
   [ISAFormat.md](https://github.com/danielmiessler/LifeOS/blob/main/LifeOS/install/LIFEOS/DOCUMENTATION/ISA/ISAFormat.md)
   separates goals, constraints, exclusions, testable claims, and unresolved work.
   [Verification.md](https://github.com/danielmiessler/LifeOS/blob/main/LifeOS/install/LIFEOS/RULES/Verification.md)
   matches probes to the user's interaction path, claim coverage, and relevant
   timing. **Local adaptation:** a compact task contract and evidence whose
   coverage matches each claim; an unavailable check leaves that claim unverified.
   We retain host-supported tools and permissions rather than importing LifeOS's
   browser mandates, personal profiles, hooks, or full artifact schema.

2. **Andrej Karpathy — autoresearch.**
   His [program.md](https://github.com/karpathy/autoresearch/blob/master/program.md)
   establishes a baseline, protects the evaluator and preparation code, and logs
   experiment versions, measurements, and keep/discard/crash outcomes while
   considering complexity. **Local adaptation:** a finite experiment ledger with
   a hypothesis, artifact version, actual observations, and disposition; preserve
   quality checks rather than weakening them to improve a score. Experiments
   share the parent's pass allowance and current authorization. We do not adopt
   the indefinite loop, automatic commits/resets, GPU assumptions, or its metric
   as a general measure of task quality.

3. **Peter Steinberger — agent-scripts.**
   The [README](https://github.com/steipete/agent-scripts/blob/main/README.md)
   identifies the canonical shared instructions and helpers.
   [docs-list.ts](https://github.com/steipete/agent-scripts/blob/main/scripts/docs-list.ts)
   inventories documentation summaries and `read_when` hints and reports missing
   metadata. **Local adaptation:** inspect a targeted documentation inventory
   before choosing checks. The upstream index does not execute or select those
   checks. No new metadata format or helper dependency is required here.

4. **Armin Ronacher — agent-stuff.**
   [agent-commands redirects to agent-stuff](https://github.com/mitsuhiko/agent-commands),
   whose README identifies Armin's personal agent package. His
   [June 12, 2025 recommendations](https://lucumr.pocoo.org/2025/6/12/agentic-coding/#tools-tools-tools)
   group critical commands in a Makefile and emphasize useful logs and actionable
   errors. **Local adaptation:** discover canonical verification commands and
   prerequisites; explain unavailable checks and the claims they leave open.
   Pi extensions, shell interception, model choices, and permission bypasses are
   not transferred.

These adaptations live in [task-contracts.md](../skills/no-mistakes/references/task-contracts.md)
and original [evaluation scenarios](../evals/scenarios.json). They require no new
runtime dependencies or personal-profile collection. Third-party collections
labelled “Karpathy skills” or “Boris setup” were not verified as owner repositories
and are not attributed to those authors.
