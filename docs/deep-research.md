# New-source research and adaptation decisions

Research date: 2026-10-08. This round starts from the local v0.4.0 draft, after
the personal-setup additions. Previously included inspirations and their sources
were excluded from the new search set. Three parallel research reviews covered
execution, retrieval/memory, and security/evaluation; supporting owner code, docs,
and papers were opened, rather than relying on search snippets.

This is a bounded research phase, not an exhaustive survey. Observations below
describe the inspected sources. Adaptations are original design choices for this
portable skill and optional Python helper, with no upstream code, prompts,
datasets, dependencies, benchmark scores, or endorsements imported.

## Execution and verification

| Primary source inspected | Supported observation | Decision for No Mistakes |
| --- | --- | --- |
| [SWE-bench grading implementation](https://github.com/SWE-bench/SWE-bench/blob/main/swebench/harness/grading.py) | Its runner-specific grader distinguishes an empty parsed result from positive evidence that tests ran, checks timeout/error markers, and cross-checks recorded exit status. | Require evidence that intended tests executed; exit zero or a pass-looking line alone is insufficient. Do not copy runner-specific parsing or claim universal test detection. |
| [Agentless procedure](https://github.com/OpenAutoCoder/Agentless/blob/main/README_swebench.md) and [reranker](https://github.com/OpenAutoCoder/Agentless/blob/main/agentless/repair/rerank.py) | Generated reproductions are validated against original code. Candidate reranking includes fallbacks when reproduction does not pass. | Use a relevant before/after reproduction where feasible. Ranking or fallback selection cannot replace required acceptance checks. |
| [Aider lint/test documentation](https://aider.chat/docs/usage/lint-test.html) | Configured lint and test commands return diagnostics; a formatter can modify files and exit nonzero without a remaining lint defect. | Interpret the actual command contract, inspect mutations, and recheck affected final artifacts. No automatic command runner is added. |
| [SWE-agent paper, v3](https://arxiv.org/html/2405.15793v3), §§3, 5.1, appendix A.1 | The studied interfaces use bounded observations and immediate edit feedback. Edit guardrails can constrain valid multi-edit work. | Keep scoped observations and refresh stale edit context. Most of this already exists here; no universal edit-window size or automatic rollback policy is adopted. |
| [OpenHands stuck detector](https://github.com/OpenHands/software-agent-sdk/blob/main/openhands-sdk/openhands/sdk/conversation/stuck_detector.py) and [QA skill](https://github.com/OpenHands/extensions/blob/main/skills/qa-changes/SKILL.md) | The detector recognizes several repetition patterns, but its context-window-error check is currently a stub. QA distinguishes a real entrypoint exercise from help/dry-run inspection. | Existing stall and real-entrypoint rules remain. Do not claim automated stuck detection or import retry, branch, publishing, or installation policies. |

## Retrieval and memory

| Primary source inspected | Supported observation | Decision for No Mistakes |
| --- | --- | --- |
| [W3C PROV-DM](https://www.w3.org/TR/prov-dm/), §§5.1.8, 5.2, 6 | Derivation, revision, and invalidation are distinct; provenance descriptions can be structurally inconsistent. Mutable version references need care. | Validate correction relationships between present memory records. Preserve deleted references without reactivating old intent. This is not PROV conformance, authenticity, or truth verification. |
| [RAGChecker paper, v1](https://arxiv.org/html/2408.08067v1), §3.3 and appendix H | Retrieval coverage and generator utilization are separate; relevant passages can also contain misleading information. Its model-based metrics need reference answers and have entailment limits. | Distinguish missing support, contradiction, and retrieved support omitted from an answer. No metric values or automatic entailment capability are claimed. |
| [Corrective RAG paper, v3](https://arxiv.org/html/2401.15884v3), §§4.2–4.5, 6 | Retrieval-quality evaluation guides different recovery paths and depends on an external trained evaluator. | Choose one bounded, claim-specific recovery step, then check whether it supplied new evidence. Lexical score and provider success cannot certify evidence quality. |
| [LangGraph memory overview](https://docs.langchain.com/oss/python/concepts/memory) and [store documentation](https://github.com/langchain-ai/docs/blob/main/src/oss/langgraph/stores.mdx) | Profiles and collections have different update/reconciliation problems; store search can expand namespace prefixes. | Keep existing exact scope matching and backend authorization requirements. Prefix search must not silently replace a requested exact scope. No new namespace abstraction is needed. |
| [Letta passage deletion API](https://docs.letta.com/api/typescript/resources/archives/subresources/passages/methods/delete) | The documented operation removes passages from database and vector storage. | Existing deletion limits already fit: describe which representations were removed, without claiming independently retained summaries or exports were erased. No new deletion connector is needed. |

## Security and evaluation

| Primary source inspected | Supported observation | Decision for No Mistakes |
| --- | --- | --- |
| [AgentDojo paper, v3](https://arxiv.org/html/2406.13352v3), §§3.4, 4.3, 5, and [task documentation](https://agentdojo.spylab.ai/concepts/task_suite_and_tasks/) | It checks task state and reports task utility and attack outcomes separately. Tool filtering has limits when legitimate and malicious actions share tools. | Add a controlled authorized-tool/wrong-argument case. Inspect requested work and attempted boundary violations separately; blanket refusal is not task completion. |
| [CaMeL paper, v2](https://arxiv.org/html/2503.18813v2), §§3.1, 5.2–5.4, 9.3, and [owner artifact](https://github.com/google-research/camel-prompt-injection) | Value provenance and invocation policies matter even when a high-level plan is trusted. Its assumptions and non-goals exclude several corruption paths; the owner warns the research code may contain security bugs. | Independently inspect destination, path, scope, and content arguments. Keep source-derived values outside trusted instructions. No interpreter, enforcement engine, or prevention guarantee is claimed. |
| Inspect AI [scoring policy](https://inspect.aisi.org.uk/scoring-policy.html), [score history](https://inspect.aisi.org.uk/eval-logs.html), and [approval documentation](https://inspect.aisi.org.uk/approval.html) | Grader failures differ from tested-agent failures; coverage and score revisions matter. Approval does not prove execution, and remote enforcement has visibility limits. | Record actor-attributed evaluation gaps, original/revised grades, and actual effect provenance. Add explicit required-verifier coverage so a missing configured gate cannot disappear from the aggregate. |
| [ToolEmu paper, v2](https://arxiv.org/pdf/2309.15817v2), §§4.3, 7, and [owner repository](https://github.com/ryoungj/ToolEmu) | Tool emulation enables controlled tests; simulator and evaluator mistakes still require validation. | Prefer deterministic local fixtures and recorders for these tests. A simulated action is not proof of a real service result. No emulator dependency is adopted. |

## Reproduced gaps and selected work

Before changing code, local synthetic reproductions showed:

- `read_memory` accepted a reciprocal cross-scope correction and a reciprocal
  cycle, hiding the original scope's intent. It also accepted nonreciprocal links.
- `verify` passed its configured format check even when the task also required a
  package check. The API had no declaration of required check names. A new optional
  declaration can enforce that configuration contract; it cannot infer the task.
- A callback's 1,040,000-character summary passed through `verify` unchanged.
  Retrieval's retained-text limits did not cover verifier diagnostics.

The selected implementation work is correction-lineage validation, explicit
required-verifier coverage, bounded retained verifier diagnostics, focused skill
guidance, and original behavioral cases. These additions must preserve failed
verdicts, fixed quality checks, existing deletion behavior, zero runtime
dependencies, current host routing, and the publishing hold.

## Deferred or unsuitable ideas

Optional source-version metadata is useful but does not authenticate a source;
without a concrete adapter need, a broader evidence-schema migration is deferred.
[Self-RAG](https://selfrag.github.io/) uses trained reflection behavior; adding
instructions does not reproduce that training or decoding procedure. Mem0 docs
did not resolve reliably in this review, so no decision relies on them.

[Can CaMeLs Talk?, v1](https://arxiv.org/html/2610.05640v1) is an October 5, 2026
preprint about cross-agent trust propagation. A worker inspected its stated
tree-topology and dependency-tracking limits. It is recent and not independently
validated here; no reported robustness rate or proposed protocol is imported.
Existing provenance boundaries remain, with original local tests rather than a
new multi-agent security framework.

Full model-based evaluators, embedding services, new paid APIs, autonomous commits,
and framework replacement are outside this round. The
[review record](deep-research-review.report.json) records actual checks and limits.
