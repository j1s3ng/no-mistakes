"""Read-only checks of project installation files, without running the host."""
from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path

from .hosts import (
    BEGIN, CLAUDE_COMMAND, CURSOR_RULE, END, HOSTS, MANIFEST_PATH, SKILL_PATH,
    _digest, _manifest_files, _merge_routing, _target, skill_payload,
)


NOTICE = "Local installation files only; host activation, tools, and model behavior were not tested."
REVIEW_INSTALL = "Review install --dry-run for the selected hosts before reinstalling."
REVIEW_LOCAL = "Preserve and review local changes before resolving ownership and reinstalling."


def doctor(project: str | Path, hosts: Sequence[str]) -> dict:
    """Collect actionable findings for explicitly selected project host profiles.

    Descendant symlinks are refused, unselected adapters and unowned extras are
    ignored, and no files or directories are created. Like install, callers must
    avoid concurrent changes; these local checks are not a filesystem sandbox.
    """
    if (not isinstance(hosts, Sequence) or isinstance(hosts, (str, bytes))
            or not hosts or any(not isinstance(host, str) or host not in HOSTS for host in hosts)):
        raise ValueError("Select one or more supported hosts")
    selected = list(dict.fromkeys(hosts))
    try:
        root = Path(project).expanduser().resolve()
        valid_project = root.is_dir()
    except (OSError, RuntimeError, TypeError, ValueError):
        raise ValueError("project must be an existing directory") from None
    if not valid_project:
        raise ValueError("project must be an existing directory")
    issues = []

    def issue(code: str, relative: str, message: str, action: str = REVIEW_INSTALL):
        issues.append({"code": code, "path": relative, "message": message, "action": action})

    def read(relative: str) -> tuple[bytes | None, bool]:
        try:
            path = _target(root, relative)
        except ValueError:
            issue("unsafe_path", relative, "Installation path is unsafe or is not a regular file.",
                  "Review symlinks, parent directories, and file types before retrying.")
            return None, False
        except OSError:
            issue("unreadable_file", relative, "Installation path could not be inspected.",
                  "Check access to this installation path and rerun doctor.")
            return None, False
        try:
            return path.read_bytes(), True
        except FileNotFoundError:
            return None, True
        except OSError:
            issue("unreadable_file", relative, "Installation file could not be read.",
                  "Check access to this installation path and rerun doctor.")
            return None, False

    owned = {}
    manifest, readable = read(MANIFEST_PATH)
    if readable:
        if manifest is None:
            issue("missing_manifest", MANIFEST_PATH, "Installation ownership manifest is missing.",
                  "Review existing skill files before installing or restoring ownership records.")
        else:
            try:
                owned = _manifest_files(manifest)
            except ValueError:
                issue("invalid_manifest", MANIFEST_PATH, "Installation ownership manifest is invalid.",
                      "Review the manifest and preserve local changes before repairing ownership.")

    managed = {f"{SKILL_PATH}/{name}": content for name, content in skill_payload().items()}
    if "claude" in selected:
        managed[".claude/commands/no-mistakes.md"] = CLAUDE_COMMAND.encode("utf-8")
    if "cursor" in selected:
        managed[HOSTS["cursor"]] = (CURSOR_RULE + _merge_routing("")).encode("utf-8")

    for relative, expected in managed.items():
        content, readable = read(relative)
        if not readable:
            continue
        if content is None:
            issue("missing_file", relative, "Expected installed skill or adapter file is missing.")
        elif relative not in owned:
            issue("unowned_file", relative, "Installed file has no valid ownership record.", REVIEW_LOCAL)
        elif _digest(content) != owned[relative]:
            issue("modified_file", relative, "Installed file differs from its recorded ownership hash.", REVIEW_LOCAL)
        elif content != expected:
            issue("outdated_file", relative, "Owned installed file differs from this package's payload.")

    for relative, digest in owned.items():
        if not relative.startswith(SKILL_PATH + "/") or relative in managed:
            continue
        content, readable = read(relative)
        if not readable:
            continue
        if content is None:
            issue("retired_record", relative, "Manifest still records a retired file that is already missing.")
        elif _digest(content) != digest:
            issue("modified_file", relative, "Retired installed file differs from its recorded ownership hash.", REVIEW_LOCAL)
        else:
            issue("retired_file", relative, "Owned installed file is absent from this package's payload.")

    routes = dict.fromkeys(HOSTS[host] for host in selected if host != "cursor")
    for relative in routes:
        content, readable = read(relative)
        if not readable:
            continue
        if content is None:
            issue("missing_route", relative, "Selected host's routing file is missing.")
            continue
        try:
            original = content.decode("utf-8")
            merged = _merge_routing(original)
        except ValueError:
            issue("invalid_route", relative, "Routing file is not UTF-8 or has malformed managed markers.",
                  "Review the routing file and its marked block before reinstalling.")
            continue
        if BEGIN not in original and END not in original:
            issue("missing_route", relative, "Selected host's No Mistakes routing block is missing.")
        elif merged != original:
            issue("outdated_route", relative, "Selected host's No Mistakes routing block is outdated.")

    return {"project": str(root), "hosts": selected, "ok": not issues,
            "issues": issues, "notice": NOTICE}
