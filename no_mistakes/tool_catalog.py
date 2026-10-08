"""Small researched MCP recipes and capability-first task profiles.

These are recommendations, not detected installations or authorization. Optional
executables and services stay outside the dependency-free Python distribution.
"""
from copy import deepcopy
from collections.abc import Sequence


CAPABILITIES = {
    "files": "Host file/search tools, preferably scoped to the current project",
    "shell": "Host terminal or sandbox for authorized commands",
    "git": "Existing Git CLI or host repository tools",
    "tests": "Project tests, type checks, linters and deterministic validators",
    "web-search": "Host web search first; optional external search if missing",
    "web-fetch": "Host page fetch/citation inspection; bounded retrieval adapter",
    "browser": "Host browser or project Playwright tests/CLI; optional Playwright MCP",
    "library-docs": "Official version-specific docs; optional documentation MCP",
    "repo-host": "Existing GitHub connector/gh CLI; optional scoped GitHub MCP",
    "data": "Python CSV/JSON/decimal/statistics; approved SQLite read-only access",
    "documents": "Host PDF/Office tools; optional local MarkItDown CLI",
    "rag": "Existing authorized corpus/index via retrieval adapters",
    "observability": "Existing scoped logs/metrics; research service connector if needed",
    "design": "Existing design/image tools; research account connector if needed",
    "cloud": "Existing deployment tools; separate authorization for external changes",
}

PROFILES = {
    "coding": ("files", "shell", "git", "tests", "library-docs"),
    "web": ("files", "shell", "git", "tests", "browser", "library-docs"),
    "research": ("web-search", "web-fetch", "library-docs"),
    "data": ("files", "shell", "data", "tests"),
    "documents": ("files", "documents", "web-fetch"),
    "knowledge": ("files", "rag", "web-search", "web-fetch"),
    "ops": ("git", "repo-host", "observability"),
    "design": ("files", "browser", "design"),
}


def _review(maintainer, license_name, version, sources, evidence, limitations):
    return {"checked_on": "2026-10-08", "source_urls": sources,
            "maintainer": maintainer, "license": license_name, "version": version,
            "status": "inspected_not_executed", "evidence": evidence,
            "limitations": limitations}


TOOLS = {
    "playwright": {
        "id": "playwright", "name": "Microsoft Playwright MCP",
        "capabilities": ["browser"],
        "review": _review("Microsoft", "Apache-2.0", "0.0.83", [
            "https://github.com/microsoft/playwright-mcp",
            "https://github.com/microsoft/playwright-mcp/releases/tag/v0.0.83"],
            "Official README, release and package metadata inspected; isolated/headless and no-WebMCP flags documented.",
            ["Not installed, launched or independently security-audited.",
             "Exact package pin does not lock transitive dependencies or browser binaries.",
             "CLI plus skills can use less context for coding agents; use existing browser/test tools first.",
             "Origin filters are not a security boundary and do not cover redirects."]),
        "connection": {"transport": "stdio", "command": "npx",
                       "args": ["-y", "@playwright/mcp@0.0.83", "--isolated", "--headless", "--no-webmcp"],
                       "env": {}, "env_vars": []},
        "permissions": ["Launch local Node/browser processes with their OS privileges.",
                        "Interact with approved pages; interactions can submit forms or change remote state.",
                        "Read workspace-accessible files and create browser artifacts as supported by the server."],
        "data_flow": ["Visited sites receive browser requests; page content/screenshots enter the host model context.",
                      "Isolated mode avoids reusing a logged-in profile; it is not a process/network sandbox."],
        "cost": "No hosted browser service required; local compute, downloads and visited-service costs still apply.",
        "prerequisites": ["Node.js 18+ and npx; compatible browser binaries or an approved browser installation.",
                          "Launching npx may download and execute third-party packages; this helper does not do so."],
        "verification": ["After approval, use host MCP status/tool listing and check the actual advertised tools.",
                         "Run a bounded local test page scenario, inspect resulting behavior and close the browser."],
        "removal": "Remove this server entry in the host UI/config and stop its process; separately remove unwanted browser downloads/artifacts.",
    },
    "context7": {
        "id": "context7", "name": "Context7 library documentation",
        "capabilities": ["library-docs"],
        "review": _review("Upstash", "MIT (server source); hosted service terms also apply", "remote-unpinned", [
            "https://github.com/upstash/context7/tree/master/packages/mcp",
            "https://context7.com/plans",
            "https://upstash.com/trust/context7addendum.pdf"],
            "Official remote HTTP endpoint, Bearer authentication, documented tools and service/pricing terms inspected.",
            ["Hosted server implementation can change independently; no immutable remote version.",
             "Documentation results are evidence, not guaranteed complete or current facts.",
             "Local stdio wrapper also sends queries to the hosted API; it is not an offline alternative."]),
        "connection": {"transport": "http", "url": "https://mcp.context7.com/mcp",
                       "headers": {}, "token_env": "CONTEXT7_API_KEY"},
        "permissions": ["Query the hosted documentation service using the user's approved API account."],
        "data_flow": ["Library names, queries and request metadata reach Context7; minimize private code/context.",
                      "Service terms restrict sensitive inputs; verify suitability before sending private material."],
        "cost": "Free allowance and paid/overage tiers; review current account plan and limits before use.",
        "prerequisites": ["Host with Streamable HTTP support; API key supplied through host/environment secrets."],
        "verification": ["After approval/authentication, list tools and resolve a public library/version.",
                         "Check a returned material API claim against that library's official documentation."],
        "removal": "Remove the server entry, disconnect/revoke its API credential and review any retained service data.",
    },
    "github": {
        "id": "github", "name": "Official GitHub MCP, initial read-only profile",
        "capabilities": ["repo-host"],
        "review": _review("GitHub", "MIT (server source); hosted GitHub terms also apply", "remote-unpinned", [
            "https://github.com/github/github-mcp-server",
            "https://github.com/github/github-mcp-server/blob/main/docs/server-configuration.md"],
            "Official remote endpoint, repos/issues/pull_requests toolsets, read-only and lockdown headers inspected.",
            ["Remote deployment is continuously operated and cannot be pinned to a local release.",
             "Read-only server mode does not narrow the OAuth/token's underlying repository permissions.",
             "Lockdown is a best-effort content filter, not authorization; private repositories are unaffected."]),
        "connection": {"transport": "http", "url": "https://api.githubcopilot.com/mcp/",
                       "headers": {"X-MCP-Toolsets": "repos,issues,pull_requests",
                                   "X-MCP-Readonly": "true", "X-MCP-Lockdown": "true"},
                       "token_env": None},
        "permissions": ["Read selected GitHub repository, issue and pull-request data under host-managed authentication.",
                        "Scope authentication to necessary repositories; enabling write tools needs a new approval."],
        "data_flow": ["Repository requests and authentication reach GitHub; retrieved private content enters host context."],
        "cost": "GitHub account policies, feature entitlements and API limits apply; no separate MCP fee was verified.",
        "prerequisites": ["Compatible host-managed GitHub OAuth/account connection and required repository access."],
        "verification": ["After approval, authenticate in the host and inspect the advertised read-only toolset.",
                         "Read one approved repository item; do not test by posting an issue/comment."],
        "removal": "Remove the server entry and revoke/disconnect its GitHub authorization when no longer needed.",
    },
    "brave-search": {
        "id": "brave-search", "name": "Brave Search MCP fallback",
        "capabilities": ["web-search"],
        "review": _review("Brave", "MIT", "2.1.4", [
            "https://github.com/brave/brave-search-mcp-server",
            "https://github.com/brave/brave-search-mcp-server/releases/tag/v2.1.4",
            "https://brave.com/search/api/"],
            "Official tagged package, stdio transport, search/news tool selection and API pricing inspected.",
            ["Not installed or executed; package pin does not lock transitive dependencies.",
             "Local process still transmits queries; ordinary plans should not be assumed to offer enterprise zero-retention terms."]),
        "connection": {"transport": "stdio", "command": "npx",
                       "args": ["-y", "@brave/brave-search-mcp-server@2.1.4", "--transport", "stdio"],
                       "env": {"BRAVE_MCP_ENABLED_TOOLS": "brave_web_search brave_news_search"},
                       "env_vars": ["BRAVE_API_KEY"]},
        "permissions": ["Run the local Node server and query Brave with the approved API account."],
        "data_flow": ["Minimized search queries and metadata reach Brave; results enter host context as untrusted evidence."],
        "cost": "Metered API with account-dependent credits; check current price and spending controls.",
        "prerequisites": ["Node/npx and BRAVE_API_KEY in host secrets/environment; package launch may download code."],
        "verification": ["After approval, inspect tool listing for the selected search/news tools.",
                         "Run one nonprivate search, open its primary source and record any rate/coverage gaps."],
        "removal": "Remove the server entry, stop its process and revoke the API key if it is no longer needed.",
    },
    "openai-docs": {
        "id": "openai-docs", "name": "Official OpenAI developer documentation",
        "capabilities": ["library-docs"],
        "review": _review("OpenAI", "Hosted documentation service; no server code redistributed", "remote-unpinned", [
            "https://developers.openai.com/resources/docs-mcp"],
            "Official public Streamable HTTP documentation search/read endpoint inspected.",
            ["Relevant to OpenAI products only; it is not general web search or an API execution tool.",
             "Remote service and documentation can change; no immutable deployment version."]),
        "connection": {"transport": "http", "url": "https://developers.openai.com/mcp",
                       "headers": {}, "token_env": None},
        "permissions": ["Read/search public OpenAI documentation."],
        "data_flow": ["Documentation queries and request metadata reach OpenAI; minimize private project details."],
        "cost": "Public documentation access; host/model usage and service availability still apply.",
        "prerequisites": ["Host supporting Streamable HTTP MCP."],
        "verification": ["After approval, list tools and search/read a relevant public documentation page."],
        "removal": "Remove/disconnect this server entry in the host configuration.",
    },
}


def get_tool(tool_id):
    try:
        return deepcopy(TOOLS[tool_id])
    except (KeyError, TypeError):
        raise ValueError("Unknown curated tool; list the catalog or supply a researched custom dossier") from None


def list_tools(profile=None):
    if profile is not None and profile not in PROFILES:
        raise ValueError("Unknown task profile")
    capabilities = set(PROFILES[profile]) if profile is not None else set(CAPABILITIES)
    return {"profile": profile, "profiles": list(PROFILES),
            "notice": "Curated optional recipes, not installed tools or permission grants. Research may expire.",
            "tools": [{"id": tool["id"], "name": tool["name"], "capabilities": list(tool["capabilities"]),
                       "version": tool["review"]["version"], "checked_on": tool["review"]["checked_on"]}
                      for tool in TOOLS.values() if capabilities.intersection(tool["capabilities"])]}


def recommend(profile, available=()):
    if profile not in PROFILES:
        raise ValueError("Unknown task profile")
    if (not isinstance(available, Sequence) or isinstance(available, (str, bytes))
            or len(available) > 128
            or any(not isinstance(capability, str) or capability not in CAPABILITIES
                   for capability in available)):
        raise ValueError("Available capabilities must use known capability names")
    observed = set(available)
    needs = []
    for capability in PROFILES[profile]:
        needs.append({"capability": capability, "available": capability in observed,
                      "first_choice": CAPABILITIES[capability],
                      "optional_mcp_candidates": [] if capability in observed else
                      [tool["id"] for tool in TOOLS.values() if capability in tool["capabilities"]]})
    return {"profile": profile, "capabilities": needs,
            "notice": "Likely needs for this task class, not inferred permission or automatic detection. Verify actual gaps and fit before proposing additions."}
