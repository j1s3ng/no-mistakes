"""Workflow helpers with local memory and explicit opt-in retrieval adapters."""
import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import re
import stat
import sys
import tempfile
import uuid

TRIGGER = re.compile(r"(?<!\S)no mistakes\.?\s*\Z", re.IGNORECASE)
DELETED_CORRECTION = "deleted-correction"


def _tool_document(path):
    """Read bounded regular files without following a selected symlink.

    Nonblocking open and descriptor checks prevent a replaced path from turning
    a read-only review into an indefinite FIFO read.
    """
    def unique_pairs(pairs):
        result = {}
        for key, value in pairs:
            if key in result:
                raise ValueError("Tool document has duplicate keys")
            result[key] = value
        return result

    try:
        before = path.lstat()
        if not stat.S_ISREG(before.st_mode):
            raise ValueError("Tool document must be a regular file without symlinks")
        descriptor = os.open(path, os.O_RDONLY | getattr(os, "O_NONBLOCK", 0)
                             | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_BINARY", 0))
    except OSError:
        raise ValueError("Tool document must be a readable regular file without symlinks") from None
    try:
        opened = os.fstat(descriptor)
        if (not stat.S_ISREG(opened.st_mode)
                or (opened.st_dev, opened.st_ino) != (before.st_dev, before.st_ino)):
            raise ValueError("Tool document changed while opening; review a regular file")
        with os.fdopen(descriptor, "rb") as stream:
            descriptor = None
            content = stream.read(262_145)
    finally:
        if descriptor is not None:
            os.close(descriptor)
    if len(content) > 262_144:
        raise ValueError("Tool document exceeds 256 KiB")
    try:
        return json.loads(content.decode("utf-8"), object_pairs_hook=unique_pairs)
    except RecursionError:
        raise ValueError("Tool document nesting is too deep") from None


def _confirm_tool_proposal(proposal):
    """Prompt a terminal operator; host approval rules still apply separately."""
    if not sys.stdin.isatty():
        raise ValueError("MCP configuration requires an interactive user decision; review the plan and use a terminal or the host's approval UI")
    print(json.dumps(proposal, indent=2, ensure_ascii=False), file=sys.stderr)
    print("Writing this native config can cause the host to connect to services or download/run third-party code. No server has been tested by this helper.", file=sys.stderr)
    phrase = "enable " + proposal["digest"][:12]
    print("Approve exactly this proposal? Type '" + phrase + "' (anything else declines): ",
          end="", file=sys.stderr, flush=True)
    try:
        answer = input()
    except EOFError:
        return False
    return answer.strip() == phrase


def activation(prompt):
    match = TRIGGER.search(prompt)
    return {"active": match is not None,
            "task": prompt[:match.start()].rstrip() if match else prompt}


def read_memory(root):
    path = root / "memory.json"
    if not path.exists():
        return []
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, list):
        raise ValueError("Memory must be a JSON array")
    ids = set()
    for entry in data:
        if not isinstance(entry, dict):
            raise ValueError("Memory entries must be objects")
        for field in ("id", "text", "source", "scope", "kind", "created_at"):
            if not isinstance(entry.get(field), str) or not entry[field].strip():
                raise ValueError(f"Memory entry requires a nonempty {field}")
        if entry["id"] in ids:
            raise ValueError("Memory entry IDs must be unique")
        ids.add(entry["id"])
        if entry["kind"] not in ("explicit", "confirmed", "inferred"):
            raise ValueError("Memory entry has an invalid kind")
        for field in ("supersedes", "superseded_by"):
            if field in entry and (not isinstance(entry[field], str) or not entry[field].strip()):
                raise ValueError(f"Memory entry has an invalid {field}")

    by_id = {entry["id"]: entry for entry in data}
    for entry in data:
        for field, reciprocal in (("supersedes", "superseded_by"),
                                  ("superseded_by", "supersedes")):
            # This established successor marker means inactive deleted history,
            # even when a separately stored record happens to use the same ID.
            if field == "superseded_by" and entry.get(field) == DELETED_CORRECTION:
                continue
            target = by_id.get(entry.get(field))
            # Missing references can record deleted history. Never repair them or
            # reactivate an entry whose correction has been forgotten.
            if target is None:
                continue
            if target["id"] == entry["id"]:
                raise ValueError("Memory correction links must not reference the same entry")
            if target["scope"] != entry["scope"]:
                raise ValueError("Memory correction links must remain in the same scope")
            if target.get(reciprocal) != entry["id"]:
                raise ValueError("Memory correction links must be reciprocal")

    checked = set()
    for entry_id in by_id:
        trail = set()
        current = entry_id
        # Each present entry is visited once across completed traversals; a
        # repeated entry in the current traversal identifies a cycle.
        while current in by_id and current not in checked:
            if current in trail:
                raise ValueError("Memory correction links must not form a cycle")
            trail.add(current)
            current = by_id[current].get("supersedes")
        checked.update(trail)
    return data


def write_memory(root, entries):
    root.mkdir(parents=True, exist_ok=True, mode=0o700)
    # Atomic replacement prevents partial writes; callers must serialize writers.
    fd, name = tempfile.mkstemp(dir=root, prefix=".memory-", suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as stream:
            json.dump(entries, stream, indent=2, ensure_ascii=False)
            stream.write("\n")
        os.replace(name, root / "memory.json")
    finally:
        if os.path.exists(name):
            os.unlink(name)


def remember(root, text, source, scope, kind, supersedes=None):
    for field, value in (("text", text), ("source", source), ("scope", scope)):
        if not isinstance(value, str) or not value.strip():
            raise ValueError(f"{field} must be a nonempty string")
    if kind not in ("explicit", "confirmed", "inferred"):
        raise ValueError("kind must be explicit, confirmed, or inferred")
    if supersedes is not None and (not isinstance(supersedes, str) or not supersedes.strip()):
        raise ValueError("supersedes must be a nonempty memory ID")
    entries = read_memory(root)
    if supersedes:
        prior = next((e for e in entries if e["id"] == supersedes), None)
        if prior is None or prior.get("superseded_by"):
            raise ValueError("Correction requires an existing active entry")
        if prior["scope"] != scope:
            raise ValueError("Correction must remain in the original scope")
    item = dict(id=uuid.uuid4().hex, text=text, source=source, scope=scope,
                kind=kind, created_at=datetime.now(timezone.utc).isoformat())
    if supersedes:
        item["supersedes"] = supersedes
        prior["superseded_by"] = item["id"]
    entries.append(item)
    write_memory(root, entries)
    return item


def context(root, query, scope=None, limit=10):
    words = set(re.findall(r"\w+", query.casefold()))
    ranked = []
    for item in read_memory(root):
        if item.get("superseded_by") or (scope and item["scope"] != scope):
            continue
        tokens = set(re.findall(r"\w+", (item["text"] + " " + item["scope"]).casefold()))
        score = len(words & tokens)
        if not words or score:
            ranked.append((score, item["created_at"], item))
    ranked.sort(key=lambda x: (x[0], x[1]), reverse=True)
    return [item for _, _, item in ranked[:limit]]


def check_report(report):
    """Check evidence record completeness, never truth or tool execution."""
    errors = []
    if not isinstance(report, dict):
        return ["Report must be an object"]
    if not isinstance(report.get("intent"), str) or not report["intent"].strip():
        errors.append("A nonempty intent is required")
    for group in ("criteria", "claims"):
        records = report.get(group)
        if not isinstance(records, list) or (group == "criteria" and not records):
            errors.append(f"{group} must be a list" + (" with at least one criterion" if group == "criteria" else ""))
            continue
        for index, record in enumerate(records):
            prefix = f"{group}[{index}]"
            if not isinstance(record, dict):
                errors.append(f"{prefix} must be an object")
                continue
            for field in ("text", "evidence"):
                if not isinstance(record.get(field), str) or not record[field].strip():
                    errors.append(f"{prefix} requires {field}")
            expected = "passed" if group == "criteria" else "verified"
            if record.get("status") != expected:
                errors.append(f"{prefix} is not {expected}")
    review = report.get("final_review")
    if not isinstance(review, dict):
        errors.append("final_review must record goal_alignment, system_fit, and side_effects")
    else:
        if not isinstance(review.get("artifact"), str) or not review["artifact"].strip():
            errors.append("final_review requires the final artifact/version inspected")
        for aspect in ("goal_alignment", "system_fit", "side_effects"):
            record = review.get(aspect)
            if not isinstance(record, dict):
                errors.append(f"final_review.{aspect} requires a review record")
                continue
            if record.get("status") != "passed":
                errors.append(f"final_review.{aspect} is not passed")
            if not isinstance(record.get("evidence"), str) or not record["evidence"].strip():
                errors.append(f"final_review.{aspect} requires evidence")
    iterations = report.get("iteration_summary")
    if not isinstance(iterations, dict):
        errors.append("iteration_summary must record passes and stop_reason")
    else:
        allowed_passes = 10
        approvals = set()
        continuations = iterations.get("continuations", [])
        if not isinstance(continuations, list):
            errors.append("iteration_summary.continuations must be a list")
        else:
            for index, continuation in enumerate(continuations):
                prefix = f"iteration_summary.continuations[{index}]"
                if not isinstance(continuation, dict):
                    errors.append(f"{prefix} must be an approval record")
                    continue
                extra = continuation.get("additional_passes")
                approval = continuation.get("approval")
                valid_extra = type(extra) is int and 1 <= extra <= 10
                valid_approval = isinstance(approval, str) and bool(approval.strip())
                if not valid_extra:
                    errors.append(f"{prefix}.additional_passes must be an integer from 1 to 10")
                if not valid_approval:
                    errors.append(f"{prefix} requires the explicit user approval reference")
                if valid_extra and valid_approval:
                    reference = approval.strip()
                    if reference in approvals:
                        errors.append(f"{prefix} reuses an approval reference")
                    else:
                        approvals.add(reference)
                        allowed_passes += extra
        passes = iterations.get("passes")
        if type(passes) is not int or not 1 <= passes <= allowed_passes:
            errors.append(f"iteration_summary.passes must be an integer from 1 to {allowed_passes}")
        if iterations.get("stop_reason") != "complete":
            errors.append("iteration_summary.stop_reason must be complete for completion")
    if not isinstance(report.get("limitations"), list):
        errors.append("limitations must be an explicit list (may be empty)")
    return errors


def graph(root):
    entries = read_memory(root)
    nodes = []
    edges = []
    source_ids = set()
    for item in entries:
        nodes.append({**item, "type": "intent"})
        source_id = "source:" + item["source"]
        if source_id not in source_ids:
            nodes.append({"id": source_id, "type": "source", "text": item["source"]})
            source_ids.add(source_id)
        edges.append({"from": item["id"], "to": source_id,
                      "relation": "supported_by", "basis": item["kind"]})
        if item.get("supersedes"):
            edges.append({"from": item["id"], "to": item["supersedes"],
                          "relation": "supersedes", "basis": "explicit"})
    return {"nodes": nodes, "edges": edges}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--memory-dir", type=Path, default=Path(".no-mistakes"))
    sub = parser.add_subparsers(dest="command", required=True)
    from .hosts import HOSTS
    setup = sub.add_parser("install", help="Install project-scoped skill and host routing without changing permissions")
    setup.add_argument("--host", action="append", choices=tuple(HOSTS), required=True)
    setup.add_argument("--project", type=Path, default=Path.cwd())
    setup.add_argument("--dry-run", action="store_true", help="Preview changes without writing files")
    diagnostic = sub.add_parser("doctor", help="Inspect local installation files without changing them")
    diagnostic.add_argument("--host", action="append", choices=tuple(HOSTS), required=True)
    diagnostic.add_argument("--project", type=Path, default=Path.cwd())
    toolbox = sub.add_parser("toolbox", help="Recommend tools and review optional MCP configuration before approval")
    tools = toolbox.add_subparsers(dest="toolbox_command", required=True)
    from .tool_catalog import CAPABILITIES, PROFILES
    listing = tools.add_parser("list", help="List curated optional MCP recipes")
    listing.add_argument("--profile", choices=tuple(PROFILES))
    inspect_tool = tools.add_parser("inspect", help="Show a curated research dossier without enabling or refreshing it")
    inspect_tool.add_argument("tool", help="Curated tool ID")
    recommendation = tools.add_parser("recommend", help="Map a task profile to likely capabilities; prefer existing tools")
    recommendation.add_argument("--profile", choices=tuple(PROFILES), required=True)
    recommendation.add_argument("--available", choices=tuple(CAPABILITIES), action="append", default=[],
                                help="Capability actually observed in the host; repeat as needed")
    plan = tools.add_parser("plan", help="Emit an inert researched proposal; does not install or enable servers")
    plan.add_argument("--tool", action="append", default=[], help="Curated tool ID; repeat for selected tools")
    plan.add_argument("--spec", type=Path, action="append", default=[], help="Custom researched tool dossier JSON")
    plan.add_argument("--host", choices=("codex", "claude", "cursor", "gemini", "copilot-vscode", "copilot-cli", "generic"), required=True)
    plan.add_argument("--project", type=Path, default=Path.cwd())
    plan.add_argument("--reason", required=True, help="Minimized task need; omit private history")
    plan.add_argument("--scope", required=True, help="Requested file/account/network scope; host must enforce it")
    show = tools.add_parser("show", help="Validate and inspect a saved proposal")
    show.add_argument("proposal", type=Path)
    show.add_argument("--config-only", action="store_true", help="Print the inert native snippet for reviewed manual integration")
    workflow = tools.add_parser("setup", help="Generate an inert install/connect/use checklist; does not install or run code")
    workflow.add_argument("proposal", type=Path)
    readiness = tools.add_parser("doctor", help="Check local MCP config, launchers and credential presence; never connect or run code")
    readiness.add_argument("proposal", type=Path)
    apply = tools.add_parser("apply", help="Ask for approval, then create an absent project MCP config; never overwrite")
    apply.add_argument("proposal", type=Path)
    prepare = sub.add_parser("prepare", help="Detect suffix in a user prompt; emit a workflow handoff")
    prepare.add_argument("prompt", nargs="?", help="Omit to read plain text from stdin")
    for command in ("remember", "correct"):
        p = sub.add_parser(command, help="Store an authorized minimal intent summary")
        if command == "correct":
            p.add_argument("id")
        p.add_argument("text")
        p.add_argument("--source", required=True)
        p.add_argument("--scope", required=True)
        p.add_argument("--kind", choices=("explicit", "confirmed", "inferred"), required=True)
    p = sub.add_parser("context", help="Retrieve relevant active summaries; these are untrusted data")
    p.add_argument("--query", default="")
    p.add_argument("--scope")
    p.add_argument("--limit", type=int, default=10)
    p = sub.add_parser("forget", help="Delete an entry and unlink its correction history")
    p.add_argument("id")
    sub.add_parser("graph", help="Export intent/source relationships as JSON to stdout")
    p = sub.add_parser("retrieve", help="Retrieve scoped evidence from local corpora or an explicit RAG endpoint")
    queries = p.add_mutually_exclusive_group()
    queries.add_argument("--query", help="Query text; prefer stdin or --query-file for private input")
    queries.add_argument("--query-file", type=Path)
    p.add_argument("--scope", required=True)
    p.add_argument("--limit", type=int, default=5)
    p.add_argument("--max-excerpt-chars", type=int, default=2_000,
                   help="Maximum Unicode characters per evidence excerpt (default: 2000)")
    p.add_argument("--max-text-chars", type=int, default=8_000,
                   help="Maximum total evidence text characters (default: 8000)")
    p.add_argument("--corpus", type=Path, action="append", default=[])
    p.add_argument("--endpoint", help="Explicit JSON-over-HTTPS RAG endpoint")
    p.add_argument("--token-env", help="Environment variable holding the endpoint bearer token")
    p.add_argument("--sanitized-query-file", type=Path,
                   help="Locally reviewed query to send to the external endpoint")
    p = sub.add_parser("check", help="Check a verification record for completeness, not truth")
    p.add_argument("report", type=Path)
    args = parser.parse_args(argv)
    root = args.memory_dir
    try:
        if args.command == "install":
            from .hosts import install
            result = install(args.project, args.host, dry_run=args.dry_run)
        elif args.command == "doctor":
            from .diagnostics import doctor
            result = doctor(args.project, args.host)
            print(json.dumps(result, indent=2, ensure_ascii=False))
            return 0 if result["ok"] else 1
        elif args.command == "toolbox":
            from .tool_catalog import get_tool, list_tools, recommend
            from .toolbox import apply_proposal, build_proposal, validate_proposal
            if args.toolbox_command == "list":
                result = list_tools(args.profile)
            elif args.toolbox_command == "inspect":
                result = get_tool(args.tool)
            elif args.toolbox_command == "recommend":
                result = recommend(args.profile, args.available)
            elif args.toolbox_command == "plan":
                definitions = [get_tool(tool_id) for tool_id in args.tool]
                definitions.extend(_tool_document(path) for path in args.spec)
                result = build_proposal(definitions, args.host, args.project, args.reason, args.scope)
            elif args.toolbox_command == "show":
                result = validate_proposal(_tool_document(args.proposal))
                if args.config_only:
                    if result["config"] is None:
                        raise ValueError("Generic proposals have no universal native config; use the host's documented setup")
                    print(result["config"], end="")
                    return 0
            elif args.toolbox_command == "setup":
                from .tool_setup import setup_workflow
                result = setup_workflow(_tool_document(args.proposal), args.proposal)
            elif args.toolbox_command == "doctor":
                from .tool_readiness import check_readiness
                result = check_readiness(_tool_document(args.proposal))
                print(json.dumps(result, indent=2, ensure_ascii=False))
                return 0 if result["local_ready"] else 1
            else:
                result = apply_proposal(_tool_document(args.proposal), _confirm_tool_proposal)
                print(json.dumps(result, indent=2, ensure_ascii=False))
                return 1 if result["status"] == "declined" else 0
        elif args.command == "prepare":
            result = activation(args.prompt if args.prompt is not None else sys.stdin.read())
            if result["active"]:
                result["instruction"] = "Apply the installed no-mistakes skill to this task."
                result["needs_task"] = not bool(result["task"])
                result["workflow"] = {
                    "initial_max_passes": 10,
                    "max_passes_per_continuation": 10,
                    "continuation_requires_user_reply": True,
                    "budget_by": "material ambiguity and unresolved integration questions",
                    "stop_early": True,
                    "ask_on_stall": True,
                    "preserve_count_across_compaction": True,
                    "chunk_tasks": True,
                    "delegate_independent_chunks": True,
                    "share_pass_budget_across_agents": True,
                }
        elif args.command in ("remember", "correct"):
            result = remember(root, args.text, args.source, args.scope, args.kind,
                              getattr(args, "id", None))
        elif args.command == "context":
            if args.limit < 1:
                raise ValueError("limit must be positive")
            result = {"untrusted_memory": context(root, args.query, args.scope, args.limit)}
        elif args.command == "forget":
            entries = read_memory(root)
            if not any(e["id"] == args.id for e in entries):
                raise ValueError("Unknown memory ID")
            entries = [e for e in entries if e["id"] != args.id]
            for entry in entries:
                for field in ("supersedes", "superseded_by"):
                    if entry.get(field) == args.id:
                        # Do not resurrect an obsolete entry when deleting a correction.
                        if field == "superseded_by":
                            entry[field] = DELETED_CORRECTION
                        else:
                            del entry[field]
            write_memory(root, entries)
            result = {"deleted": args.id}
        elif args.command == "graph":
            result = graph(root)
        elif args.command == "retrieve":
            from .integrations import ContextBudget, LocalCorpusRetriever, RetrievalRequest, retrieve
            from .http_adapter import JsonHttpRetriever
            if not args.corpus and not args.endpoint:
                raise ValueError("Provide --corpus, --endpoint, or both")
            if args.token_env and not args.endpoint:
                raise ValueError("--token-env requires --endpoint")
            budget = ContextBudget(max_excerpt_chars=args.max_excerpt_chars,
                                   max_text_chars=args.max_text_chars)
            query = (args.query_file.read_text(encoding="utf-8") if args.query_file else
                     args.query if args.query is not None else sys.stdin.read())
            providers = [LocalCorpusRetriever(path, name=f"local-{index + 1}")
                         for index, path in enumerate(args.corpus)]
            if args.endpoint:
                providers.append(JsonHttpRetriever("http-rag", args.endpoint, token_env=args.token_env))
            sanitizer = None
            if args.sanitized_query_file:
                reviewed = args.sanitized_query_file.read_text(encoding="utf-8").strip()
                sanitizer = lambda original: reviewed
            result = retrieve(RetrievalRequest(query, args.scope, args.limit), providers,
                              sanitize_query=sanitizer, budget=budget)
            print(json.dumps(result, indent=2, ensure_ascii=False))
            return 1 if result["gaps"] else 0
        else:
            errors = check_report(json.loads(args.report.read_text(encoding="utf-8")))
            result = {"complete": not errors, "errors": errors,
                      "notice": "Record completeness only; evidence was not independently verified."}
            print(json.dumps(result, indent=2))
            return 1 if errors else 0
        print(json.dumps(result, indent=2, ensure_ascii=False))
        return 0
    except (OSError, ValueError, KeyError, TypeError) as error:
        print(f"no-mistakes: {error}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
