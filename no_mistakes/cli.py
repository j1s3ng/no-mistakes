"""Workflow helpers with local memory and explicit opt-in retrieval adapters."""
import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import re
import sys
import tempfile
import uuid

TRIGGER = re.compile(r"(?<!\S)no mistakes\.?\s*\Z", re.IGNORECASE)


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
    for entry in data:
        if not isinstance(entry, dict):
            raise ValueError("Memory entries must be objects")
        for field in ("id", "text", "source", "scope", "kind", "created_at"):
            if not isinstance(entry.get(field), str) or not entry[field].strip():
                raise ValueError(f"Memory entry requires a nonempty {field}")
        if entry["kind"] not in ("explicit", "confirmed", "inferred"):
            raise ValueError("Memory entry has an invalid kind")
        for field in ("supersedes", "superseded_by"):
            if field in entry and (not isinstance(entry[field], str) or not entry[field].strip()):
                raise ValueError(f"Memory entry has an invalid {field}")
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
    if not all(value.strip() for value in (text, source, scope)):
        raise ValueError("Text, source, and scope must be nonempty")
    entries = read_memory(root)
    if supersedes:
        prior = next((e for e in entries if e["id"] == supersedes), None)
        if prior is None or prior.get("superseded_by"):
            raise ValueError("Correction requires an existing active entry")
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
    for item in entries:
        nodes.append({**item, "type": "intent"})
        source_id = "source:" + item["source"]
        if not any(n["id"] == source_id for n in nodes):
            nodes.append({"id": source_id, "type": "source", "text": item["source"]})
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
        if args.command == "prepare":
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
                            entry[field] = "deleted-correction"
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
