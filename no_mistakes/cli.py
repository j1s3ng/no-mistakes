"""Local workflow helpers. No network access, model calls, or automatic execution."""
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
