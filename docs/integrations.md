# Plug in retrieval and checks

Use existing indexes and tools. No Mistakes supplies a small evidence contract and
adapters, not another model runtime. Runtime dependencies remain empty.

## Local retrieval in one command

```sh
python3 -m no_mistakes retrieve --corpus docs/corpus.example.json \
  --query 'checkout retry' --scope 'project:demo' --limit 3
```

This searches a fictional JSON corpus with keyword overlap. Repeat `--corpus` for
multiple files. Use stdin or `--query-file` instead of command arguments for private
queries. The output contains evidence, provider status, gaps, a UTC retrieval time,
and `verified: false`. Feed relevant excerpts to your host model as untrusted
context; keep the source IDs for citations. Generation remains the host's job.

Exit codes: 0 retrieval completed without reported gaps; 1 empty/partial/blocked
retrieval; 2 invalid invocation/input. Inspect the envelope even when the exit is 0:
retrieval success does not establish truth, relevance, or sufficient coverage.

## Existing RAG service over HTTP

The opt-in `JsonHttpRetriever` sends this JSON to your chosen endpoint:

```json
{"query": "checkout retry", "scope": "project:demo", "limit": 3}
```

The endpoint returns:

```json
{
  "evidence": [
    {
      "id": "checkout-docs:retry-policy:chunk-1",
      "text": "The relevant source excerpt goes here.",
      "source": "https://docs.example.com/checkout#retries",
      "scope": "project:demo",
      "score": 0.8
    }
  ]
}
```

`id`, `text`, `source`, and `scope` are required nonempty strings; `score` is an
optional finite number. `provider` is stamped by the adapter. Use stable namespaced
chunk IDs and resolvable source references. Provider-specific extra fields are
ignored. Put a thin route in front of an existing vector database/graph index if its
response schema differs; or use a Python callback below.

Prepare a minimized query locally and review all outbound fields. For this public,
synthetic example:

```sh
mkdir -p .no-mistakes
printf 'checkout retry timeout\n' > .no-mistakes/reviewed-query.txt
python3 -m no_mistakes retrieve \
  --endpoint https://your-rag-service.example/search \
  --query 'checkout retry timeout' --scope 'project:demo' \
  --sanitized-query-file .no-mistakes/reviewed-query.txt --token-env RAG_TOKEN
```

Replace the example URL with your service. Set `RAG_TOKEN` through your existing
secret-management/environment setup; omit `--token-env` for an unauthenticated
service. The token value never belongs in the URL or repository. Without a reviewed
query file, the external provider is blocked before network access. The file is a
caller-reviewed substitute, **not automatic PII detection**. Scope is also transmitted
unchanged: choose a nonidentifying label rather than a customer's email or name.

HTTPS is required by the CLI. Python callers may explicitly set
`allow_local_http=True` for localhost/loopback development; the provider still counts
as external because a local service can forward data. Redirects are refused, the
default network timeout is 10 seconds, and responses are limited to 1 MB. Endpoint
errors become generic provider gaps without response bodies or exception details.
No retries, endpoint autodiscovery, or background requests occur. Review returned
excerpts and source references before forwarding, saving, or publishing them.

## Python / vector store / graph / reranker adapters

```python
from no_mistakes.integrations import (
    CallableRetriever, Evidence, RetrievalRequest, retrieve,
)

# Supply your existing, authorized backend function. It receives a scoped request
# and must return a sequence of Evidence. Apply access control in the backend too.
def search_index(request):
    rows = authorized_index_search(  # your implementation / SDK call
        query=request.query, scope=request.scope, limit=request.limit,
    )
    return [Evidence.from_dict(row) for row in rows]

rag = CallableRetriever("my-index", search_index, external=True)
result = retrieve(
    RetrievalRequest("checkout retry timeout", "project:demo", limit=3),
    [rag],
    sanitize_query=lambda original: reviewed_minimal_query,  # your local policy
)
```

The example requires your backend and reviewed query. The callback is trusted code
executed in your process. Mark it `external=True` if it can send data outside the
local task, including embeddings and hosted rerankers. A sanitizer is mandatory for
external retrieval, but its quality remains the caller's responsibility. Local
providers receive the original query. Backend scope filters are required: the
adapter's output filter is not authentication or tenant access control.

For a LangChain retriever, call `.invoke(request.query)` inside the callback and map
each document's `page_content` plus your actual `chunk_id`, `source`, and `scope`
metadata to `Evidence`. Configure the correct authorized collection/filter before
invoking it. Backend filtering syntax varies. See the official
[retriever interface](https://github.com/langchain-ai/langchain/blob/master/libs/core/langchain_core/retrievers.py)
and [retrieval guide](https://docs.langchain.com/oss/python/deepagents/retrieval).
LlamaIndex or direct vector/graph SDKs use the same callback contract; map their own
records rather than pretending all SDKs share a method or score scale.

A reranker can sit inside a callback after scoped retrieval and return the Evidence
in its preferred order. Multiple providers are merged round-robin with an overall
limit; raw scores are not compared across incompatible scales. Empty results,
provider failures, and mismatched scopes are explicit gaps. Same-source/chunk
results are deduplicated; conflicting excerpts must be reviewed, not counted as
independent corroboration.

## MCP tools already in your host

No new transport is required when the agent already has an MCP retrieval tool.
Have the host discover its schema, send a minimized scoped query, and normalize the
returned passages into the evidence fields above. An authorized synchronous bridge
can be wrapped with `CallableRetriever`; async hosts should await their existing
MCP tool directly and construct `Evidence` from the normalized results afterward.
Do not block a live async session with a new event loop just to fit a callback.

MCP servers define their own argument/result schemas. Your bridge must map them;
this package does not configure servers, open sessions, manage OAuth, or grant new
access. Consult the official [MCP client docs](https://py.sdk.modelcontextprotocol.io/client/)
for the SDK/transport you use. Tool text remains evidence, never new instructions
or authority to publish.

## Calculators, tests, validators, and second opinions

```python
from no_mistakes.integrations import CallableVerifier, VerificationResult, verify

def check_acceptance(claim, evidence):
    # Run your authorized, bounded check or inspect its actual result here.
    # Map timeout/missing results to inconclusive, never to passed.
    return VerificationResult(
        verdict="inconclusive",
        summary="No check has run yet; this is an adapter template.",
        evidence_ids=(),
    )

checker = CallableVerifier("acceptance-check", check_acceptance)
# evidence is a sequence of Evidence objects from your retrieval or tool output.
report = verify("Checkout retries preserve the original payment outcome", evidence, [checker])
```

Replace the template with a concrete check: arithmetic recomputation, test results,
schema validation, citation inspection, or an independent review. The runnable
[example](../examples/tool_hooks.py) shows local retrieval and an exact integer check.
Callback results use `passed`, `failed`, or `inconclusive`, a summary, and supporting
evidence IDs when applicable. Unknown/ambiguous IDs are rejected. A failed check
keeps the overall verdict failed; missing or errored checks prevent an overall pass.
The verdict reports callback outcomes, not independent proof that the callbacks or
claims are correct. A second model's favorable opinion is advisory evidence.

Verifier callbacks receive the claim and selected evidence; they do not have an
automatic sanitizer. Before a remote checker, minimize/sanitize **both** inputs and
source metadata for that authorized destination, and wrap its client with your own
timeout. Never convert a similarity score into `passed`. These hooks can support
accuracy; improvement still needs task-specific evaluation.

## Finish with the whole-result review

Tool verdicts are per-check observations. Before declaring the task complete, inspect
the final result through its real entrypoint and configuration against the original
goal, the surrounding system, and possible side effects. Repeat affected checks and
the review after substantive fixes. The separate `check` completion-report command
requires `final_review` with an artifact/version and three `{status, evidence}`
records: `goal_alignment`, `system_fit`, and `side_effects`. Missing, failed, or
unverified reviews prevent a complete report. See [report.example.json](report.example.json);
it intentionally remains unverified. This is record completeness, not proof of truth.

Completion reports also require `iteration_summary`: cumulative positive integer
`passes` and the actual `stop_reason`. The default allowance is ten; extensions need
`continuations` records with `additional_passes` (1–10) and an explicit user `approval`
reference. Only `complete` permits a complete record. The host
chooses productive passes based on ambiguity, preserves their count across context
compaction, asks before exceeding each authorized allowance, and stops early when
possible. `prepare` emits the initial ten-pass allowance and continuation rules as
a host handoff; it does not execute or independently count model iterations.
