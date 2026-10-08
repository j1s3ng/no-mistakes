"""Read-only local MCP setup observations; never start or contact a server.

The report is a bounded snapshot, not a runtime, authentication, version, or
security check. Environment presence refers only to this helper process.
"""
from __future__ import annotations

from datetime import date
import errno
import os
from pathlib import Path
import shutil
import stat

from .hosts import _target
from .toolbox import MAX_PROPOSAL_BYTES, validate_proposal


_NOTICE = (
    "Read-only local snapshot: no package was downloaded, command executed, "
    "server contacted, or file written. local_ready covers only an exact native "
    "configuration match, executable presence, and named credentials present "
    "in this helper's environment; the host may use a different environment. "
    "Package versions, browser binaries, other prerequisites, remote availability, "
    "authentication, permissions, and effective scope remain unverified. "
    "Connect and run a narrow smoke check in the host after user approval."
)


def _config_status(proposal: dict) -> str:
    if proposal["host"] == "generic":
        return "manual_host_setup"
    root = Path(proposal["project"])
    expected = proposal["config"].encode("utf-8")
    try:
        if root.is_symlink():
            return "unsafe_path"
        target = _target(root, proposal["target"])
        # Nonblocking open also prevents a concurrent replacement with a FIFO
        # from hanging this otherwise local presence check.
        flags = (os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0)
                 | getattr(os, "O_NONBLOCK", 0) | getattr(os, "O_BINARY", 0))
        descriptor = os.open(target, flags)
        with os.fdopen(descriptor, "rb") as stream:
            if not stat.S_ISREG(os.fstat(stream.fileno()).st_mode):
                return "unsafe_path"
            observed = stream.read(min(len(expected) + 1, MAX_PROPOSAL_BYTES))
        return "matches_proposal" if observed == expected else "differs_manual_review"
    except FileNotFoundError:
        return "missing"
    except ValueError:
        return "unsafe_path"
    except OSError as error:
        # Filesystem exception text can contain paths or private content.
        if error.errno in (errno.ELOOP, errno.ENOTDIR, errno.EISDIR):
            return "unsafe_path"
        return "unreadable"


def _executable(command: str, project: Path) -> dict:
    # Report a name, never shutil.which's resolved path or a custom private path.
    name = command.replace("\\", "/").rsplit("/", 1)[-1]
    if os.name != "nt" and "\\" in command:
        return {"name": name, "status": "manual_check"}
    candidate = Path(command)
    if not candidate.is_absolute() and candidate.parent != Path("."):
        candidate = project / candidate
    elif not candidate.is_absolute() and ("/" in command or "\\" in command):
        # Path('./server') loses its explicit directory in .parent.
        candidate = project / candidate
    lookup = str(candidate) if candidate.is_absolute() else command
    try:
        found = shutil.which(lookup)
    except OSError:
        return {"name": name, "status": "manual_check"}
    return {"name": name, "status": "found" if found is not None else "missing"}


def check_readiness(proposal: dict, *, today: date | None = None) -> dict:
    """Validate a proposal and observe local configuration, commands, and names.

    No secret value, resolved executable path, existing configuration content,
    or raw filesystem exception is included in the returned report. Relative
    executable paths are interpreted from the proposal's project directory.
    Tampered and expired proposals fail validation rather than becoming reports.
    """
    canonical = validate_proposal(proposal, today=today)
    root = Path(canonical["project"])
    config_status = _config_status(canonical)
    issues = []
    config_actions = {
        "missing": "Review and apply the proposal, then rerun this local check.",
        "differs_manual_review": (
            "Review and manually merge the existing host configuration. Exact "
            "byte comparison cannot verify a merged setup; verify it in the host."
        ),
        "manual_host_setup": "Configure the generic host manually from the reviewed proposal.",
        "unsafe_path": "Review symlinks and nonregular configuration paths manually.",
        "unreadable": "Check local read permissions and rerun this local check.",
    }
    if config_status in config_actions:
        issues.append({"code": "config_" + config_status,
                       "action": config_actions[config_status]})

    tools = []
    local_ready = config_status == "matches_proposal"
    for tool in canonical["tools"]:
        connection = tool["connection"]
        executables = []
        credential_names = []
        if connection["transport"] == "stdio":
            command = connection["command"]
            executables.append(_executable(command, root))
            if command.replace("\\", "/").rsplit("/", 1)[-1].lower() in (
                    "npx", "npx.cmd", "npx.exe"):
                executables.extend(_executable(name, root) for name in ("node", "npm"))
            credential_names = connection["env_vars"]
        elif connection["token_env"] is not None:
            credential_names = [connection["token_env"]]

        for executable in executables:
            if executable["status"] != "found":
                local_ready = False
                action = (
                    "Install or configure the reviewed executable after user approval, "
                    "then rerun this local check."
                    if executable["status"] == "missing" else
                    "Check the reviewed executable path manually on the host platform."
                )
                issues.append({"code": "executable_" + executable["status"],
                               "tool": tool["id"],
                               "action": executable["name"] + ": " + action})

        credentials = []
        for name in credential_names:
            present = bool(os.environ.get(name, "").strip())
            credentials.append({"name": name, "status": "present" if present else "missing"})
            if not present:
                local_ready = False
                issues.append({"code": "credential_missing", "tool": tool["id"],
                               "action": "Provide " + name + " through the host's supported "
                               "secret mechanism; do not paste its value into the proposal."})

        tools.append({"id": tool["id"], "executables": executables,
                      "credentials": credentials,
                      "prerequisites": list(tool["prerequisites"]),
                      "runtime_status": "not_checked", "authentication_status": "not_checked",
                      "smoke_status": "not_run"})
        issues.append({"code": "runtime_verification_required", "tool": tool["id"],
                       "action": "Check documented versions and other prerequisites manually; "
                       "after approval, connect in the host, inspect authentication and "
                       "actual server status, and run a narrow task-specific smoke check."})

    return {"project": canonical["project"], "host": canonical["host"],
            "digest": canonical["digest"], "local_ready": local_ready,
            "config": {"status": config_status}, "tools": tools,
            "issues": issues, "notice": _NOTICE}
