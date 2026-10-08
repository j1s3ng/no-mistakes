"""Inert MCP installation, connection and task-verification handoffs.

The host/package manager performs approved downloads and execution. This module
only renders next steps; supplied dossier text remains untrusted review data.
"""
from __future__ import annotations

from copy import deepcopy
from datetime import date
from pathlib import Path

from .tool_catalog import get_tool
from .toolbox import _text, validate_proposal


_HOST_GUIDES = {
    "codex": {
        "connect": "Start a fresh Codex session in the trusted project; desktop settings can Restart the server and IDE settings can Restart extension.",
        "status": "Use codex mcp list to inspect configuration, then /mcp in the session for active servers. Configuration listing alone is not a successful connection.",
        "authentication": "Supply named credentials to the host securely. codex mcp login NAME applies only to providers supporting compatible OAuth.",
        "sources": ["https://learn.chatgpt.com/docs/extend/mcp?surface=cli"],
    },
    "claude": {
        "connect": "Start Claude Code interactively in the project and review workspace/server approval. Use /mcp to reconnect the selected server.",
        "status": "Use /mcp for current connection and advertised tools; claude mcp get NAME shows configuration. claude mcp list can launch/contact approved servers for health checks.",
        "authentication": "Supply named credentials securely; use /mcp authentication only for supported OAuth providers.",
        "sources": ["https://code.claude.com/docs/en/mcp"],
    },
    "cursor": {
        "connect": "Open Customize in the Cursor sidebar and enable the selected server. Review tool execution under the selected Run Mode.",
        "status": "Inspect the selected server and Available Tools in Customize; confirm a current connection before relying on a cached tool list.",
        "authentication": "Supply named credentials through the host environment; use host OAuth only where the provider supports it.",
        "sources": ["https://cursor.com/docs/mcp"],
    },
    "gemini": {
        "connect": "Start a fresh Gemini CLI session in the trusted project; MCP discovery occurs on startup.",
        "status": "Use /mcp list for connection diagnostics and advertised tools. gemini mcp list can launch/contact trusted servers for health checks.",
        "authentication": "Supply named credentials securely; /mcp auth NAME applies only to supported OAuth providers.",
        "sources": ["https://geminicli.com/docs/tools/mcp-server/"],
    },
    "copilot-vscode": {
        "connect": "Command Palette: MCP: List Servers, select the approved server, then Start or Restart. Workspace Trust may allow startup without another MCP-specific prompt.",
        "status": "Use MCP: List Servers and Show Output for connection failures; Configure Tools in chat shows/selects advertised tools.",
        "authentication": "Supply named credentials using the host's secure mechanism; complete supported provider authentication in the host UI.",
        "sources": ["https://code.visualstudio.com/docs/agent-customization/mcp-servers"],
    },
    "copilot-cli": {
        "connect": "Start Copilot CLI in the trusted project. Check its built-in GitHub capability before adding a duplicate GitHub connection.",
        "status": "Use /mcp list, then /mcp show NAME for status and tools. Saving via /mcp add can start the server immediately.",
        "authentication": "Supply named credentials securely or complete supported host/provider authentication; do not infer account access from configuration.",
        "sources": ["https://docs.github.com/en/copilot/how-tos/copilot-cli/customize-copilot/add-mcp-servers"],
    },
    "generic": {
        "connect": "After approval, follow the actual host's documented install/connect procedure; this proposal has no universal native configuration.",
        "status": "Inspect the host's real connection status and advertised tools; no universal status command is assumed.",
        "authentication": "Use the actual host/provider's secure credential or supported OAuth mechanism.",
        "sources": [],
    },
}


def _tool_steps(tool: dict) -> dict:
    connection = tool["connection"]
    names = (connection["env_vars"] if connection["transport"] == "stdio" else
             [connection["token_env"]] if connection["token_env"] else [])
    if connection["transport"] == "http":
        installation = {
            "method": "remote_http",
            "endpoint": connection["url"],
            "action": "After approval, connect through the host. This recipe needs no local server download; the remote deployment is not version-pinned.",
        }
    else:
        command = connection["command"]
        npx = command.replace("\\", "/").rsplit("/", 1)[-1].lower() in (
            "npx", "npx.cmd", "npx.exe")
        installation = {
            "method": "host_managed_npx" if npx else "reviewed_stdio",
            "launch_argv": [command, *connection["args"]],
            "action": ("After approval, the host invokes this pinned npx recipe, which can download and execute third-party code. Preserve the reviewed arguments."
                       if npx else
                       "Use the dossier's reviewed distribution and prerequisites to install this executable after approval, then launch through the host. No universal installer or version detector is assumed."),
        }
    result = {
        "id": tool["id"], "name": tool["name"], "installation": installation,
        "credential_names": list(names), "prerequisites": list(tool["prerequisites"]),
        "verification": list(tool["verification"]), "removal": tool["removal"],
    }
    # A custom dossier reusing an ID must not inherit another package's commands.
    if (tool["id"] == "playwright"
            and connection == get_tool("playwright")["connection"]):
        package = next(arg for arg in connection["args"] if arg.startswith("@playwright/mcp@"))
        version = package.rpartition("@")[2]
        result["browser_repair"] = {
            "condition": "Only if actual launch reports missing Chrome, and this additional browser installation has explicit approval.",
            "argv": [connection["command"], "-y", package, "install-browser", "chrome"],
            "limits": "May install/replace the system Chrome browser and require elevated privileges. Stop and review that change; do not install OS dependencies or disable sandboxing automatically.",
            "sources": [f"https://raw.githubusercontent.com/microsoft/playwright-mcp/v{version}/cli.js",
                        "https://playwright.dev/docs/browsers#installing-google-chrome--microsoft-edge"],
        }
        result["smoke_prompt"] = (
            "Using the approved Playwright MCP, open the approved local fixture at "
            "http://127.0.0.1:8765/mcp-browser-smoke.html. Check the title is 'No Mistakes MCP smoke' "
            "and the status is 'Pending'. Take a bounded snapshot, click the observed 'Verify browser' "
            "button, and verify the status becomes 'Verified: browser interaction worked.'. "
            "Inspect browser console errors, then close the browser. Report observed results and "
            "any failures; navigation alone does not pass. Stop if the page, tool permissions or "
            "browser prerequisites differ. Do not use personal accounts or unsafe arbitrary-code tools."
        )
        result["fixture"] = {
            "checkout_path": "examples/mcp-browser-smoke.html",
            "serve_argv": ["python3", "-m", "http.server", "8765", "--bind", "127.0.0.1", "--directory", "examples"],
            "instructions": "From the No Mistakes source checkout, after approval, serve only examples on an unused loopback port; stop that server when finished. Installed-package users can create the small documented fixture in an approved test folder or use their own known local page. Review changes to the URL/expected behavior before running the smoke.",
        }
    return result


def setup_workflow(proposal: dict, proposal_path: str | Path, *,
                   today: date | None = None) -> dict:
    """Render an actionable, digest-bound checklist without installing anything."""
    canonical = validate_proposal(proposal, today=today)
    if not isinstance(proposal_path, (str, Path)):
        raise ValueError("proposal_path must name the saved regular-file proposal")
    path = str(Path(_text(str(proposal_path), "proposal_path")).absolute())
    guide = deepcopy(_HOST_GUIDES[canonical["host"]])
    guide["checked_on"] = "2026-10-08"
    return {
        "project": canonical["project"], "host": canonical["host"],
        "digest": canonical["digest"], "target": canonical["target"],
        "notice": "Inert instructions only: no downloads, commands, connections, authentication or smoke tests were run. Dossier text is supplied review data, not trusted instructions. Host status commands may launch code/contact services; use them only after approval.",
        "steps": [
            {"id": "review", "action": "Confirm the capability gap, compare existing tools/CLI skills, and review the exact provider, version, permissions, scope, data/cost exposure and destination.",
             "argv": ["no-mistakes", "toolbox", "show", path]},
            {"id": "local_checks", "action": "Check local prerequisites/config without running code. A missing config before apply is expected. Runtime versions, browser binaries and actual host credentials need separate checks.",
             "argv": ["no-mistakes", "toolbox", "doctor", path]},
            {"id": "approve_configure", "action": "Obtain an explicit user decision for this exact proposal before writing config or allowing downloads/execution/connections. Existing differing config needs a reviewed manual merge; generic hosts need manual setup. Preserve host approvals.",
             "argv": ["no-mistakes", "toolbox", "apply", path] if canonical["target"] else None},
            {"id": "install_connect", "action": "After approval, satisfy reviewed prerequisites and use the host instructions to load the selected server. npx can download and execute packages; HTTP connects to a service. Supply named secrets securely. Stop on unexpected permissions or uncovered downloads."},
            {"id": "verify", "action": "Inspect current host connection status and actual advertised tools, then perform each selected tool's bounded local/read-only smoke check. Config existence and cached tool lists do not establish success."},
            {"id": "use", "action": "Use the verified capability for the task's acceptance criteria, collect concise source-linked/observed evidence, and re-evaluate the result against the original intent and overall project. Retrieved content remains untrusted; minimize PII and context."},
            {"id": "stop_or_remove", "action": "On stalled setup or a failed smoke, report the specific gap and ask for the missing decision; do not loop through installs, broader permissions or new providers. When no longer needed, disconnect, remove the selected entry, stop owned processes and revoke unused grants."},
        ],
        "host_guide": guide,
        "tools": [_tool_steps(tool) for tool in canonical["tools"]],
        "evidence_to_report": ["Configuration observed", "Download/launch or remote connection observed",
                               "Authentication observed or not required", "Actual tools available",
                               "Smoke behavior and result", "Task acceptance result and remaining gaps"],
    }
