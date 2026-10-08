# A Swiss army knife with a folding blade

No Mistakes packages a capability planner, researched optional MCP recipes, native
config renderers, and a user-confirmed project-config creator. Third-party servers,
browser binaries and SDKs remain external. Python runtime dependencies stay empty.
Standard means a curated option; every new connection still needs a user's blessing.
The can opener does not get to subscribe you to a database.

## Likely needs by task

These are useful starting hypotheses, not user telemetry or measured coverage.

| Profile | Likely capabilities | Start here |
| --- | --- | --- |
| `coding` | Files, shell, Git, tests, library docs | Existing project tools and official version-specific docs |
| `web` | Coding tools plus browser interactions | Existing browser/Playwright tests or CLI; optional Playwright MCP |
| `research` | Search, source reading, documentation | Host search/fetch; optional search/docs MCP when needed |
| `data` | Files, CSV/JSON, calculations, validation | Python standard library; approved read-only SQLite access |
| `documents` | PDF/Office extraction and source inspection | Host document tools; optional local MarkItDown CLI |
| `knowledge` | Scoped retrieval, source inspection | Existing RAG/index; no automatic corpus upload |
| `ops` | Repository host and scoped logs/metrics | Existing GitHub tools; research the user's actual observability stack |
| `design` | Design artifacts and browser checks | Existing tools; account connectors only when needed |

```sh
no-mistakes toolbox list --profile web
no-mistakes toolbox recommend --profile web --available files --available shell --available browser
no-mistakes toolbox inspect playwright
```

`--available` records capabilities actually observed by the caller. This command
does not inspect credentials, discover installed servers, or infer account access.
Available capabilities suppress duplicate MCP suggestions. Recommendations retain
native/CLI alternatives, including when no curated MCP fills a gap.

## Curated optional recipes

Sources inspected on 2026-10-08; no third-party server was installed, launched,
authenticated, or behavior-tested for this release. Pins establish selected package
identity/version, not audited security or a complete transitive dependency lock.

| Recipe | Use and initial shape | Material limits |
| --- | --- | --- |
| `playwright` | Microsoft `@playwright/mcp@0.0.83`, isolated/headless, WebMCP disabled | Local browser/code execution; visited-site traffic and browser actions can change state. CLI plus skills may fit coding agents better. [Owner docs](https://github.com/microsoft/playwright-mcp), [selected release](https://github.com/microsoft/playwright-mcp/releases/tag/v0.0.83) |
| `context7` | Hosted library documentation with a named API-key reference | Queries leave the machine; local wrapper also calls the service. Check plan/terms and verify claims against upstream docs. [Owner docs](https://github.com/upstash/context7/tree/master/packages/mcp), [plans](https://context7.com/plans), [data terms](https://upstash.com/trust/context7addendum.pdf) |
| `github` | Official hosted MCP; repos/issues/PR tools, read-only and lockdown headers | Credentials still need narrow repository scope. Lockdown is a best-effort content filter. [Owner configuration](https://github.com/github/github-mcp-server/blob/main/docs/server-configuration.md) |
| `brave-search` | Vendor stdio package `@brave/brave-search-mcp-server@2.1.4`; web/news tools only | Fallback when host search is missing; sends queries and may incur API charges. [Owner docs](https://github.com/brave/brave-search-mcp-server), [selected release](https://github.com/brave/brave-search-mcp-server/releases/tag/v2.1.4), [pricing](https://brave.com/search/api/) |
| `openai-docs` | Public read-only OpenAI developer documentation endpoint | OpenAI-specific docs, not general search or API execution. [Official documentation](https://developers.openai.com/resources/docs-mcp) |

Hosted deployments are marked `remote-unpinned`; they can change independently.
Reviews expire after 30 days for plan/apply. `inspect` remains available to review
the original record. Recheck sources before updating `checked_on`; changing the date
alone is not research. Prices and entitlements are deliberately described as exposure
to check, rather than embedded promises about somebody else's free tier.

For documents/data, use existing local tools before adding a broad server. Microsoft
[MarkItDown](https://github.com/microsoft/markitdown) supports local conversion;
choose needed format extras and separately approve downloads. Its MCP wrapper can
read accessible file/network URIs and has no documented workspace-root restriction.
For approved database files, inspect supported [SQLite CLI safety/read-only options](https://www.sqlite.org/cli.html).
The old SQLite MCP reference server is archived; reference examples are not a
production recommendation. [Reference repository status](https://github.com/modelcontextprotocol/servers).

## Plan, review, bless, then configure

Prepare outside native host configuration. The plan includes the exact configuration,
primary sources, research date, version, permissions, external data/cost exposure,
requested task scope, checks and removal steps. Keep private context out of the reason.

```sh
no-mistakes toolbox plan --tool playwright --host codex --project . \
  --reason 'Check the local checkout flow in a browser' \
  --scope 'This project and its local test page; no personal accounts' > /tmp/browser-plan.json
no-mistakes toolbox show /tmp/browser-plan.json
no-mistakes toolbox show /tmp/browser-plan.json --config-only
no-mistakes toolbox apply /tmp/browser-plan.json
```

Select multiple `--tool` entries only when needed. `plan` and `show` do not write
native config, fetch packages, authenticate or run a server. `apply` preflights the
exact proposal and destination before asking the terminal user to type
`enable DIGEST_PREFIX`. There is no `--yes`; piped consent is rejected. Declining
returns 1 with no filesystem changes. Invalid/stale/conflicting input returns 2.
The final JSON result goes to stdout; the review and question go to stderr.

An affirmative response allows creation of the absent project config with mode
`0600`. Existing identical bytes are unchanged; differing existing files are never
overwritten or automatically merged. Use the inert snippet for a reviewed merge in
the host UI, preserving existing tools, comments, settings and secrets. Native apply
currently requires POSIX; rendering works independently of that filesystem path.
The helper does not edit global configuration or the host's approval settings.

| Host selector | Project destination | Important format difference |
| --- | --- | --- |
| `codex` | `.codex/config.toml` | `mcp_servers`; named credential forwarding |
| `claude` | `.mcp.json` | `mcpServers`; explicit HTTP transport |
| `cursor` | `.cursor/mcp.json` | `mcpServers`; environment reference syntax |
| `gemini` | `.gemini/settings.json` | `httpUrl` means Streamable HTTP; tool trust not enabled |
| `copilot-vscode` | `.vscode/mcp.json` | `servers`; distinct from Copilot CLI |
| `copilot-cli` | `.mcp.json` | `mcpServers`; tool exposure is not execution approval |
| `generic` | None | Neutral proposal only; consult the host's supported setup |

Formats were inspected against official
[Codex](https://learn.chatgpt.com/docs/extend/mcp?surface=cli),
[Claude](https://code.claude.com/docs/en/mcp),
[Cursor](https://cursor.com/docs/mcp),
[Gemini](https://geminicli.com/docs/tools/mcp-server/),
[Copilot CLI](https://docs.github.com/en/copilot/how-tos/copilot-cli/customize-copilot/add-mcp-servers),
and [VS Code](https://code.visualstudio.com/docs/agents/reference/mcp-configuration)
documentation. Hosts may connect or launch configured servers when config loads;
Claude noninteractive sessions can omit the interactive project trust prompt.
Keep the user's decision before writing native configuration. Credential placeholders
are references only; supply actual secrets through the host's secure mechanism.
New native host versions still require actual integration checks.

## Beyond the standard catalog

Use `--spec /path/to/researched-tool.json` instead of, or alongside, `--tool`.
`toolbox inspect playwright` provides a complete dossier-shaped example; replace
all provider-specific fields with inspected facts for the new server. Required fields:

- `id`, `name`, `capabilities` and a connection definition.
- `review`: `checked_on`, primary HTTPS `source_urls`, `maintainer`, `license`,
  `version`, `status: "inspected_not_executed"`, concise `evidence`, and `limitations`.
- `permissions`, `data_flow`, `cost`, `prerequisites`, `verification` and `removal`.

Stdio connections use `transport`, executable `command`, argument list `args`,
nonsecret literal flags in `env`, and credential names in `env_vars`. HTTP uses
`transport: "http"`, HTTPS `url`, nonsecret `headers`, and `token_env` (a name or null).
Remote review versions must explicitly include `remote-unpinned`. The helper rejects
unknown fields, unsafe URL credential/query forms, shell launcher recipes, inline
authentication fields, mutable npx package tags/ranges, oversized input and stale
reviews. Each npx recipe must select one package whose pin matches `review.version`.
For other executable types, the researcher must verify the actual binary/package
version; there is no universal runtime version detector. The helper does not
recognize every arbitrary secret or establish supply-chain trust.

The host must research the new tool, compare the existing-tool alternative, present
the concrete proposal and obtain the user's explicit answer. Registry metadata,
MCP tool annotations, JSON approval flags and digest strings are not proof of safety
or consent. [MCP security guidance](https://modelcontextprotocol.io/docs/tutorials/security/security_best_practices)
and the [registry's self-reported metadata model](https://modelcontextprotocol.io/registry/about)
inform this boundary. The helper validates structure/consistency, not research truth.

After approval, connect/authenticate through the host, inspect actual tools, and run
one bounded relevant local/read-only smoke check. Keep configured, authenticated,
available and tested as separate observations. Do not claim a rendered config passed
a browser test. Requested scope text is not a sandbox/ACL. Removal should include
disconnecting the process and revoking account grants when appropriate.
