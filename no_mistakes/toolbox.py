"""Reviewable, project-scoped MCP configuration proposals, using only stdlib.

Planning never runs a command or contacts a server. Review records are supplied
data, not facts authenticated by this validator. Applying creates one new native
configuration only after a caller-provided confirmation callback returns True.
The callback is a user-interface boundary, not a cryptographic consent proof.
Existing configurations require a manual merge unless their bytes match exactly.
"""
from __future__ import annotations

from collections.abc import Callable
from copy import deepcopy
from datetime import date, datetime
import hashlib
import json
import os
from pathlib import Path
import re
import unicodedata
from urllib.parse import urlsplit
import uuid

from .hosts import _target


HOSTS = ("codex", "claude", "cursor", "gemini", "copilot-vscode",
         "copilot-cli", "generic")
TARGETS = {"codex": ".codex/config.toml", "claude": ".mcp.json",
           "cursor": ".cursor/mcp.json", "gemini": ".gemini/settings.json",
           "copilot-vscode": ".vscode/mcp.json", "copilot-cli": ".mcp.json"}
MAX_TOOLS = 20
MAX_SPEC_BYTES = 16 * 1024
MAX_PROPOSAL_BYTES = 256 * 1024
MAX_REVIEW_AGE_DAYS = 30
_ENV = re.compile(r"[A-Z_][A-Z0-9_]*\Z")
_ID = re.compile(r"[a-z][a-z0-9_-]{0,63}\Z")
_SECRET = re.compile(r"(?:TOKEN|SECRET|PASSWORD|PASSWD|API[-_]?KEY|PRIVATE[-_]?KEY|"
                     r"CREDENTIAL|AUTH)", re.I)
_FLAGS = re.compile(r"[A-Za-z0-9_.-]+(?:[ ,][A-Za-z0-9_.-]+)*\Z")
_PINNED_PACKAGE = re.compile(
    r"(?:@[a-z0-9_.-]+/)?[a-z0-9_.-]+@\d+\.\d+\.\d+"
    r"(?:-[0-9A-Za-z.-]+)?(?:\+[0-9A-Za-z.-]+)?\Z")
_TOOL_FIELDS = {"id", "name", "capabilities", "review", "connection",
                "permissions", "data_flow", "cost", "prerequisites",
                "verification", "removal"}
_REVIEW_FIELDS = {"checked_on", "source_urls", "maintainer", "license", "version",
                  "status", "evidence", "limitations"}
_NOTICE = ("Review metadata is supplied evidence, not independently verified facts. "
           "Planning does not install, execute, authenticate, or test servers. "
           "Native configuration may launch servers or transmit data when the host loads it. "
           "The requested scope is not an enforced filesystem, account, or network boundary.")


def _json(value: object) -> str:
    try:
        return json.dumps(value, ensure_ascii=False, sort_keys=True,
                          separators=(",", ":"), allow_nan=False)
    except (TypeError, ValueError, RecursionError):
        raise ValueError("Expected bounded JSON data") from None


def _bounded(value: object, maximum: int, label: str) -> str:
    encoded = _json(value)
    try:
        size = len(encoded.encode("utf-8"))
    except UnicodeError:
        raise ValueError(f"{label} contains an invalid Unicode surrogate") from None
    if size > maximum:
        raise ValueError(f"{label} exceeds the {maximum}-byte limit")
    return encoded


def _text(value: object, label: str, *, maximum: int = 8192) -> str:
    if (not isinstance(value, str) or not value.strip() or len(value) > maximum
            or any(unicodedata.category(char) in ("Cc", "Cs") for char in value)):
        raise ValueError(f"{label} must be nonempty text without control characters")
    return value


def _fields(value: object, expected: set[str], label: str) -> dict:
    if not isinstance(value, dict) or set(value) != expected:
        raise ValueError(f"{label} has missing or unsupported fields")
    return value


def _texts(value: object, label: str, *, nonempty: bool = True) -> list[str]:
    if (not isinstance(value, list) or len(value) > 128
            or (nonempty and not value)):
        raise ValueError(f"{label} must be a bounded {'nonempty ' if nonempty else ''}list")
    return [_text(item, label) for item in value]


def _url(value: object, label: str) -> str:
    value = _text(value, label, maximum=4096)
    try:
        parsed = urlsplit(value)
        port = parsed.port
        if (parsed.scheme != "https" or not parsed.hostname or parsed.username is not None
                or parsed.password is not None or parsed.query or parsed.fragment
                or "?" in value or "#" in value or "\\" in value
                or any(char.isspace() for char in value)
                or (port is not None and not 1 <= port <= 65535)):
            raise ValueError
    except ValueError:
        raise ValueError(f"{label} must be HTTPS without credentials, query, or fragment") from None
    return value


def _env_name(value: object, label: str) -> str:
    value = _text(value, label, maximum=128)
    if _ENV.fullmatch(value) is None:
        raise ValueError(f"{label} must name an environment variable, not its value")
    return value


def _literal_flags(value: object, label: str, *, headers: bool = False) -> dict[str, str]:
    if not isinstance(value, dict) or len(value) > 32:
        raise ValueError(f"{label} must be a bounded object of nonsecret flags")
    result = {}
    for key, item in value.items():
        _text(key, label, maximum=128)
        if headers:
            if re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9-]*", key) is None:
                raise ValueError("Invalid HTTP header name")
        else:
            _env_name(key, label)
        item = _text(item, label, maximum=256)
        if (_SECRET.search(key) or key.lower() in ("authorization", "cookie", "set-cookie",
                                                   "proxy-authorization")
                or _FLAGS.fullmatch(item) is None
                or re.search(r"(?:bearer|basic)\s", item, re.I)
                or _SECRET.search(item)):
            raise ValueError(f"{label} accepts nonsecret literal flags only; use named credentials")
        result[key] = item
    return result


def _today(value: date | None) -> date:
    if value is None:
        return date.today()
    if not isinstance(value, date) or isinstance(value, datetime):
        raise ValueError("today must be a date")
    return value


def _check_npx(command: str, args: list[str], version: str) -> None:
    if command.replace("\\", "/").rsplit("/", 1)[-1].lower() not in ("npx", "npx.cmd", "npx.exe"):
        return
    packages = []
    index = 0
    while index < len(args):
        argument = args[index]
        if argument in ("-y", "--yes", "--no"):
            index += 1
            continue
        if argument in ("-p", "--package"):
            index += 1
            if index >= len(args):
                raise ValueError("npx requires an exact package version")
            packages.append(args[index])
        elif argument.startswith("--package="):
            packages.append(argument.split("=", 1)[1])
        elif argument.startswith("-"):
            raise ValueError("Unsupported npx launcher option; use an explicit pinned package")
        else:
            if not packages:
                packages.append(argument)
            break
        index += 1
    if not packages or any(_PINNED_PACKAGE.fullmatch(item) is None for item in packages):
        raise ValueError("npx packages require exact numeric versions; mutable tags/ranges are refused")
    if len(packages) != 1 or packages[0].rpartition("@")[2] != version:
        raise ValueError("npx recipes require one pinned package matching review.version")


def _connection(value: object, version: str) -> dict:
    if not isinstance(value, dict):
        raise ValueError("connection must be an object")
    if value.get("transport") == "stdio":
        _fields(value, {"transport", "command", "args", "env", "env_vars"}, "stdio connection")
        command = _text(value["command"], "command", maximum=1024)
        if any(char.isspace() for char in command) or "${" in command or "$" in command:
            raise ValueError("command must be one executable name or path, without substitutions")
        if Path(command).name.lower() in ("sh", "bash", "zsh", "fish", "cmd", "cmd.exe",
                                         "powershell", "powershell.exe", "pwsh"):
            raise ValueError("Shell launch recipes are unsupported")
        args = _texts(value["args"], "args", nonempty=False)
        for argument in args:
            if (re.search(r"(?:authorization|bearer|password|passwd|api[-_]?key|secret|token)"
                          r"(?:$|=|:|\s)", argument, re.I)
                    or "${" in argument):
                raise ValueError("Inline credentials and argument substitutions are unsupported")
        _check_npx(command, args, version)
        env = _literal_flags(value["env"], "env")
        env_vars = [_env_name(item, "env_vars") for item in
                    _texts(value["env_vars"], "env_vars", nonempty=False)]
        if len(set(env_vars)) != len(env_vars) or set(env_vars) & set(env):
            raise ValueError("Environment names must be unique and separate from literal flags")
        return {"transport": "stdio", "command": command, "args": args,
                "env": env, "env_vars": env_vars}
    if value.get("transport") == "http":
        _fields(value, {"transport", "url", "headers", "token_env"}, "http connection")
        url = _url(value["url"], "connection URL")
        headers = _literal_flags(value["headers"], "headers", headers=True)
        token_env = value["token_env"]
        if token_env is not None:
            token_env = _env_name(token_env, "token_env")
        if "remote-unpinned" not in version.lower():
            raise ValueError("Hosted HTTP review.version must explicitly say remote-unpinned")
        return {"transport": "http", "url": url, "headers": headers, "token_env": token_env}
    raise ValueError("Supported connection transports are stdio and http")


def _tool(value: object, today: date) -> dict:
    _bounded(value, MAX_SPEC_BYTES, "Tool spec")
    value = _fields(value, _TOOL_FIELDS, "Tool spec")
    identifier = _text(value["id"], "tool id", maximum=64)
    if _ID.fullmatch(identifier) is None:
        raise ValueError("Tool id must use lowercase letters, numbers, underscores, and hyphens")
    review = _fields(value["review"], _REVIEW_FIELDS, "review")
    checked = _text(review["checked_on"], "checked_on", maximum=10)
    try:
        checked_date = date.fromisoformat(checked)
    except ValueError:
        raise ValueError("checked_on must be an ISO date") from None
    if checked_date.isoformat() != checked or checked_date > today:
        raise ValueError("checked_on must be an ISO date that is not in the future")
    if (today - checked_date).days > MAX_REVIEW_AGE_DAYS:
        raise ValueError("Tool review is stale; refresh its sources and checked_on before planning or applying")
    if review["status"] != "inspected_not_executed":
        raise ValueError("review.status must be inspected_not_executed")
    reviewed = {"checked_on": checked,
                "source_urls": [_url(item, "source URL") for item in
                                _texts(review["source_urls"], "source_urls")],
                "maintainer": _text(review["maintainer"], "maintainer"),
                "license": _text(review["license"], "license"),
                "version": _text(review["version"], "version"),
                "status": "inspected_not_executed",
                "evidence": _text(review["evidence"], "evidence"),
                "limitations": _texts(review["limitations"], "limitations")}
    result = {"id": identifier, "name": _text(value["name"], "name"),
              "capabilities": _texts(value["capabilities"], "capabilities"),
              "review": reviewed,
              "connection": _connection(value["connection"], reviewed["version"])}
    for key in ("permissions", "data_flow", "prerequisites", "verification"):
        result[key] = _texts(value[key], key)
    for key in ("cost", "removal"):
        result[key] = _text(value[key], key)
    return result


def _reference(name: str, host: str) -> str:
    return "${env:" + name + "}" if host in ("cursor", "copilot-vscode") else "${" + name + "}"


def _native(tools: list[dict], host: str) -> str | None:
    if host == "generic":
        return None
    if host == "codex":
        lines = []
        for tool in tools:
            connection = tool["connection"]
            lines.append("[mcp_servers." + json.dumps(tool["id"]) + "]")
            if connection["transport"] == "stdio":
                lines += ["command = " + json.dumps(connection["command"], ensure_ascii=False),
                          "args = " + json.dumps(connection["args"], ensure_ascii=False),
                          "env = { " + ", ".join(json.dumps(key) + " = " + json.dumps(item)
                                                  for key, item in sorted(connection["env"].items())) + " }",
                          "env_vars = " + json.dumps(connection["env_vars"])]
            else:
                lines.append("url = " + json.dumps(connection["url"], ensure_ascii=False))
                if connection["headers"]:
                    lines.append("http_headers = { " + ", ".join(
                        json.dumps(key) + " = " + json.dumps(item)
                        for key, item in sorted(connection["headers"].items())) + " }")
                if connection["token_env"] is not None:
                    lines.append("bearer_token_env_var = " + json.dumps(connection["token_env"]))
            lines.append("")
        return "\n".join(lines)
    servers = {}
    for tool in tools:
        connection = tool["connection"]
        entry = {}
        if connection["transport"] == "stdio":
            if host in ("claude", "copilot-vscode", "copilot-cli"):
                entry["type"] = "stdio"
            entry["command"] = connection["command"]
            entry["args"] = connection["args"]
            env = dict(connection["env"])
            env.update({name: _reference(name, host) for name in connection["env_vars"]})
            if env:
                entry["env"] = env
        else:
            if host in ("claude", "copilot-vscode"):
                entry["type"] = "http"
            entry["httpUrl" if host == "gemini" else "url"] = connection["url"]
            headers = dict(connection["headers"])
            if connection["token_env"] is not None:
                headers["Authorization"] = "Bearer " + _reference(connection["token_env"], host)
            if headers:
                entry["headers"] = headers
        if host == "gemini":
            entry["trust"] = False
        if host == "copilot-cli":
            if connection["transport"] == "http":
                entry["type"] = "http"
            entry["tools"] = ["*"]
        servers[tool["id"]] = entry
    return json.dumps({"servers" if host == "copilot-vscode" else "mcpServers": servers},
                      ensure_ascii=False, indent=2, sort_keys=True) + "\n"


def build_proposal(tools: list[dict], host: str, project: Path | str, reason: str,
                   scope: str, *, today: date | None = None) -> dict:
    """Build an inert proposal with all supplied review data and exact native text.

    Native targets stay within an existing project directory; scope records the
    requested task/file/account/network scope. Rendering is portable. No source
    URL is fetched and no secret reference is resolved. Reviews expire in 30 days.
    """
    current = _today(today)
    if not isinstance(host, str) or host not in HOSTS:
        raise ValueError("Select a supported toolbox host")
    scope = _text(scope, "scope")
    reason = _text(reason, "reason")
    if not isinstance(project, (str, Path)):
        raise ValueError("project must be an existing directory")
    _text(str(project), "project")
    supplied_root = Path(project)
    if supplied_root.is_symlink():
        raise ValueError("Refusing a symlink project directory")
    root = supplied_root.resolve()
    if not root.is_dir():
        raise ValueError("project must be an existing directory")
    if not isinstance(tools, list) or not 1 <= len(tools) <= MAX_TOOLS:
        raise ValueError(f"Select between 1 and {MAX_TOOLS} tools")
    validated = [_tool(tool, current) for tool in tools]
    if len({tool["id"] for tool in validated}) != len(validated):
        raise ValueError("Tool ids must be unique")
    proposal = {"schema_version": 1, "project": str(root), "scope": scope,
                "host": host, "reason": reason, "tools": validated,
                "target": TARGETS.get(host), "config": _native(validated, host),
                "notice": _NOTICE}
    proposal["digest"] = hashlib.sha256(_json(proposal).encode("utf-8")).hexdigest()
    _bounded(proposal, MAX_PROPOSAL_BYTES, "Proposal")
    return proposal


def validate_proposal(proposal: dict, *, today: date | None = None) -> dict:
    """Regenerate and compare every field; a serialized approved flag is invalid.

    The digest detects changes to a reviewed document, not malicious authorship:
    anybody can construct a new proposal. Applying still requires live consent.
    """
    serialized = _bounded(proposal, MAX_PROPOSAL_BYTES, "Proposal")
    _fields(proposal, {"schema_version", "project", "scope", "host", "reason", "tools",
                       "target", "config", "notice", "digest"}, "Proposal")
    if (not isinstance(proposal["digest"], str)
            or re.fullmatch(r"[0-9a-f]{64}", proposal["digest"]) is None):
        raise ValueError("Proposal requires a valid review digest")
    canonical = build_proposal(proposal["tools"], proposal["host"], proposal["project"],
                               proposal["reason"], proposal["scope"], today=today)
    if serialized != _json(canonical):
        raise ValueError("Proposal changed or has unsupported fields; rebuild and review it")
    return canonical


def _snapshot(root: Path, relative: str, expected: bytes) -> tuple[list[tuple], bool]:
    target = _target(root, relative)
    records = []
    for path in (root, *list(target.parents)[:len(Path(relative).parts) - 1][::-1], target):
        if path.is_symlink():
            raise ValueError("Refusing a symlink configuration path")
        try:
            details = path.stat()
        except FileNotFoundError:
            records.append((str(path), None))
        else:
            records.append((str(path), details.st_dev, details.st_ino, details.st_mode,
                            details.st_size, details.st_mtime_ns))
    if not root.is_dir():
        raise ValueError("project must remain an existing directory")
    if target.exists():
        descriptor = os.open(target, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0))
        with os.fdopen(descriptor, "rb") as stream:
            same = stream.read(len(expected) + 1) == expected
        if not same:
            raise ValueError(f"Existing {relative} differs; manually merge the reviewed config. "
                             "Automatic merging and overwriting are unsupported.")
        return records, True
    return records, False


def _create(root: Path, relative: str, content: bytes) -> None:
    """Place complete bytes with an exclusive hard link; never replace a target."""
    flags = os.O_RDONLY | getattr(os, "O_DIRECTORY", 0) | getattr(os, "O_NOFOLLOW", 0)
    root_fd = os.open(root, flags)
    parent_fd = root_fd
    made_parent = False
    temporary = None
    own_temporary = False
    parts = Path(relative).parts
    try:
        if len(parts) == 2:
            try:
                os.mkdir(parts[0], mode=0o700, dir_fd=root_fd)
                made_parent = True
            except FileExistsError:
                pass
            parent_fd = os.open(parts[0], flags, dir_fd=root_fd)
        temporary = ".no-mistakes-toolbox-" + uuid.uuid4().hex
        descriptor = os.open(temporary, os.O_CREAT | os.O_EXCL | os.O_WRONLY
                             | getattr(os, "O_NOFOLLOW", 0), 0o600, dir_fd=parent_fd)
        own_temporary = True
        with os.fdopen(descriptor, "wb") as stream:
            os.fchmod(stream.fileno(), 0o600)
            stream.write(content)
            stream.flush()
            os.fsync(stream.fileno())
        try:
            os.link(temporary, parts[-1], src_dir_fd=parent_fd,
                    dst_dir_fd=parent_fd, follow_symlinks=False)
        except FileExistsError:
            raise ValueError("Configuration appeared after confirmation; review again. No file was overwritten.") from None
    finally:
        if own_temporary:
            try:
                os.unlink(temporary, dir_fd=parent_fd)
            except FileNotFoundError:
                pass
        if parent_fd != root_fd:
            os.close(parent_fd)
        if made_parent:
            try:
                os.rmdir(parts[0], dir_fd=root_fd)
            except OSError:
                pass  # Successful configurations keep their parent directory.
        os.close(root_fd)


def apply_proposal(proposal: dict, confirm: Callable[[dict], bool], *,
                   today: date | None = None) -> dict:
    """Validate and preflight, request live consent, recheck, then create one file.

    Native application requires POSIX directory descriptors; proposal rendering
    remains portable. Run applies serially. Exclusive placement prevents overwrites; this is not a
    sandbox against a hostile process concurrently replacing project directories.
    No command, network request, authentication, or server health check is run.
    """
    canonical = validate_proposal(proposal, today=today)
    if not callable(confirm):
        raise ValueError("confirm must be a callable user confirmation interface")
    if canonical["host"] == "generic":
        raise ValueError("generic proposals have no native target; review and configure the host manually")
    if os.name != "posix":
        raise ValueError("Native apply requires POSIX directory descriptors; manually merge the reviewed config on this platform")
    root = Path(canonical["project"])
    relative = canonical["target"]
    content = canonical["config"].encode("utf-8")
    before, unchanged = _snapshot(root, relative, content)
    result = {"project": str(root), "host": canonical["host"], "target": relative,
              "digest": canonical["digest"], "status": "unchanged"}
    if unchanged:
        return result
    review_copy = deepcopy(canonical)
    if confirm(review_copy) is not True:
        result["status"] = "declined"
        return result
    if (_json(review_copy) != _json(canonical)
            or _json(validate_proposal(proposal, today=today)) != _json(canonical)):
        raise ValueError("Proposal changed during confirmation; rebuild and review it")
    after, _ = _snapshot(root, relative, content)
    if before != after:
        raise ValueError("Configuration path changed during confirmation; review again")
    _create(root, relative, content)
    result["status"] = "created"
    return result
