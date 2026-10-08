"""Fixed synthetic shared-API comparison. No network, external services or user history.

Run this same file in separate processes for both trusted implementation snapshots:
python examples/compare_snapshot.py PATH_TO_SNAPSHOT [OUTPUT_JSON]
No candidate-only kwargs are used. Expectations are contract-oriented criteria,
not an estimate of accuracy or model quality. Failures show this probe's mismatch,
not a universal determination of whether an older release promised a new feature.
"""
import argparse
import contextlib
import hashlib
import inspect
import io
import json
from pathlib import Path
import sys
import tempfile

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument("snapshot", type=Path, help="trusted source checkout containing no_mistakes")
parser.add_argument("output", type=Path, nargs="?", help="new JSON output file (default: new temporary directory)")
options = parser.parse_args()
snapshot = options.snapshot.resolve()
if not (snapshot / "no_mistakes" / "integrations.py").is_file():
    parser.error("snapshot must contain no_mistakes/integrations.py")
if options.output is not None and (options.output.exists() or not options.output.parent.is_dir()):
    parser.error("output must be a new file in an existing directory")
sys.path.insert(0, str(snapshot))
from no_mistakes import cli
from no_mistakes.integrations import (
    CallableRetriever, CallableVerifier, ContextBudget, Evidence,
    LocalCorpusRetriever, RetrievalRequest, VerificationResult, retrieve, verify,
)

# Check module origins so an unrelated installed package cannot supply the observations.
import no_mistakes
import no_mistakes.integrations as integrations
for module in (no_mistakes, cli, integrations):
    if not Path(module.__file__).resolve().is_relative_to(snapshot):
        parser.error("imported module did not come from the selected snapshot")

observations = []


def record(name, expected, observed, satisfied, area, change_kind="existing-behavior"):
    observations.append(dict(name=name, area=area, change_kind=change_kind,
                             expected=expected, observed=observed, satisfied=bool(satisfied)))


def run(name, callback, area):
    try:
        callback()
    except Exception as exc:
        record(name, "probe completes without an unexpected exception",
               dict(exception=type(exc).__name__, message=str(exc)), False, area)


def ev(key, text="Synthetic useful evidence", scope="project:A", **kwargs):
    return Evidence(key, text, "synthetic:" + key, scope, **kwargs)


def provider(name, values, external=False):
    return CallableRetriever(name, lambda request: values, external=external)


def gaps(envelope):
    return [entry["reason"] for entry in envelope["gaps"]]


def subclass_retrieval():
    class SerializerOverride(Evidence):
        def to_dict(self):
            result = super().to_dict()
            result.update(id="forged-id", text="Z" * 10_000,
                          source="forged-source", scope="project:other",
                          provider="forged-provider", injected_extra="extra")
            return result
    item = SerializerOverride("original-id", "A" * 80, "synthetic:original", "project:A")
    out = retrieve(RetrievalRequest("synthetic", "project:A", 1), [provider("local", [item])],
                   budget=ContextBudget(max_excerpt_chars=12, max_text_chars=12))
    row = out["evidence"][0]
    observed = dict(id=row["id"], source=row["source"], scope=row["scope"],
                    provider=row["provider"], text_chars=len(row["text"]),
                    retained_text_chars=out["context_budget"]["retained_text_chars"],
                    original_chars=row["original_chars"], truncated=row["truncated"],
                    extra_fields=sorted(set(row) - set(Evidence.to_dict(item))))
    expected = dict(id="original-id", source="synthetic:original", scope="project:A",
                    provider="local", text_chars=12, retained_text_chars=12,
                    original_chars=80, truncated=True, extra_fields=[])
    record("subclass_serializer_cannot_replace_bounded_evidence_or_provenance", expected,
           observed, observed == expected, "retrieval", "hardening")


def ordinary_retrieval():
    out = retrieve(RetrievalRequest("synthetic", "project:A", 3), [
        provider("first", [ev("a"), ev("b")]), provider("second", [ev("c"), ev("d")])])
    observed = dict(ids=[e["id"] for e in out["evidence"]], verified=out["verified"],
                    trust=out["trust"], providers=[p["accepted"] for p in out["providers"]])
    expected = dict(ids=["a", "c", "b"], verified=False, trust="untrusted", providers=[2, 1])
    record("ordinary_round_robin_and_trust", expected, observed, observed == expected, "retrieval")


def dedup_retrieval():
    duplicate = ev("a")
    out = retrieve(RetrievalRequest("synthetic", "project:A", 3), [
        provider("first", [duplicate, ev("b")]), provider("second", [duplicate, ev("c")])])
    observed = [e["id"] for e in out["evidence"]]
    record("retrieval_deduplicates_shared_provenance", ["a", "b", "c"], observed,
           observed == ["a", "b", "c"], "retrieval")


def scope_retrieval():
    out = retrieve(RetrievalRequest("synthetic", "project:A"), [
        provider("local", [ev("other", scope="project:B"), ev("same")])])
    observed = dict(ids=[e["id"] for e in out["evidence"]], scope_gap="scope_mismatch" in gaps(out))
    expected = dict(ids=["same"], scope_gap=True)
    record("retrieval_scope_isolation", expected, observed, observed == expected, "retrieval")


def failure_retrieval():
    def fail(request):
        raise RuntimeError("synthetic-secret-should-not-leak")
    out = retrieve(RetrievalRequest("synthetic", "project:A"), [
        CallableRetriever("broken", fail, external=False), provider("good", [ev("good")])])
    observed = dict(ids=[e["id"] for e in out["evidence"]],
                    failed="retriever_failed" in gaps(out),
                    leaked="synthetic-secret-should-not-leak" in json.dumps(out))
    expected = dict(ids=["good"], failed=True, leaked=False)
    record("retrieval_failure_isolation_and_error_redaction", expected, observed,
           observed == expected, "retrieval")


def sanitization_retrieval():
    calls = []
    external = CallableRetriever("external", lambda request: calls.append(request.query) or [ev("a")])
    blocked = retrieve(RetrievalRequest("synthetic-private-query", "project:A"), [external])
    blocked_calls = list(calls)
    allowed = retrieve(RetrievalRequest("synthetic-private-query", "project:A"), [external],
                       sanitize_query=lambda query: "synthetic-clean-query")
    observed = dict(blocked_calls=blocked_calls, blocked_ids=[e["id"] for e in blocked["evidence"]],
                    blocked_gap="sanitization_required" in gaps(blocked),
                    allowed_calls=calls, allowed_ids=[e["id"] for e in allowed["evidence"]],
                    private_query_returned="synthetic-private-query" in json.dumps(allowed))
    expected = dict(blocked_calls=[], blocked_ids=[], blocked_gap=True,
                    allowed_calls=["synthetic-clean-query"], allowed_ids=["a"], private_query_returned=False)
    record("external_callback_requires_and_receives_sanitized_query", expected, observed,
           observed == expected, "retrieval")


def conflict_retrieval():
    out = retrieve(RetrievalRequest("synthetic", "project:A"), [
        provider("first", [ev("a", "long initial text")]),
        provider("second", [ev("a", "long conflicting text"), ev("b")])])
    observed = dict(ids=[e["id"] for e in out["evidence"]],
                    conflict_gaps=gaps(out).count("evidence_conflict"))
    expected = dict(ids=["b"], conflict_gaps=2)
    record("retrieval_excludes_conflicting_full_text_provenance", expected, observed,
           observed == expected, "retrieval")


def truncated_retrieval():
    out = retrieve(RetrievalRequest("synthetic", "project:A", 3), [
        provider("local", [ev("a", "A" * 20), ev("b", "B" * 20), ev("c", "C" * 20)])],
        budget=ContextBudget(max_excerpt_chars=6, max_text_chars=10))
    observed = dict(lengths=[len(e["text"]) for e in out["evidence"]],
                    originals=[e["original_chars"] for e in out["evidence"]],
                    truncated=[e["truncated"] for e in out["evidence"]],
                    retained=out["context_budget"]["retained_text_chars"],
                    omitted=out["context_budget"]["omitted_items"],
                    exhausted="text_budget_exhausted" in gaps(out))
    expected = dict(lengths=[6, 4], originals=[20, 20], truncated=[True, True],
                    retained=10, omitted=1, exhausted=True)
    record("retrieval_excerpt_and_aggregate_limits_are_truthful", expected, observed,
           observed == expected, "retrieval")


def prior_truncation():
    item = ev("short", "partial", original_chars=100, truncated=True)
    out = retrieve(RetrievalRequest("synthetic", "project:A"), [provider("local", [item])])
    row = out["evidence"][0]
    observed = dict(text=row["text"], original_chars=row["original_chars"],
                    truncated=row["truncated"], gap="excerpt_truncated" in gaps(out))
    expected = dict(text="partial", original_chars=100, truncated=True, gap=True)
    record("retrieval_preserves_preexisting_truncation", expected, observed,
           observed == expected, "retrieval")


def metadata_retrieval():
    out = retrieve(RetrievalRequest("synthetic", "project:A"), [
        provider("local", [Evidence("a", "synthetic text", "x" * 40, "project:A")])],
        budget=ContextBudget(max_metadata_chars=20))
    observed = dict(ids=[e["id"] for e in out["evidence"]], limited="metadata_limit" in gaps(out))
    expected = dict(ids=[], limited=True)
    record("retrieval_rejects_provenance_instead_of_clipping_it", expected, observed,
           observed == expected, "retrieval")


def corpus_retrieval():
    with tempfile.TemporaryDirectory(prefix="synthetic-corpus-") as folder:
        path = Path(folder) / "corpus.json"
        path.write_text(json.dumps([ev("less", "alpha").to_dict(), ev("more", "alpha beta").to_dict(),
                                    ev("other", "alpha beta", "project:B").to_dict()]))
        out = retrieve(RetrievalRequest("alpha beta", "project:A"), [LocalCorpusRetriever(path)])
        observed = dict(ids=[e["id"] for e in out["evidence"]], scores=[e["score"] for e in out["evidence"]])
        expected = dict(ids=["more", "less"], scores=[1.0, 0.5])
        record("ordinary_local_corpus_ranking_and_scope", expected, observed,
               observed == expected, "retrieval")


def memory_entry(key, scope="project:A", **links):
    return dict(id=key, text="Synthetic preference " + key, source="synthetic:user",
                scope=scope, kind="explicit", created_at="2026-01-01T00:00:00Z", **links)


def outcome(callback):
    try:
        value = callback()
        return dict(raised=None, returned_ids=[e["id"] for e in value] if isinstance(value, list) else None)
    except Exception as exc:
        return dict(raised=type(exc).__name__, returned_ids=None)


def malformed_memory(name, entries):
    with tempfile.TemporaryDirectory(prefix="synthetic-memory-") as folder:
        root = Path(folder)
        path = root / "memory.json"
        payload = json.dumps(entries, indent=2) + "\n"
        path.write_text(payload)
        read = outcome(lambda: cli.read_memory(root))
        context = outcome(lambda: cli.context(root, "", "project:A"))
        write = outcome(lambda: cli.remember(root, "Synthetic new preference", "synthetic:new", "project:A", "explicit"))
        observed = dict(read_rejected=read["raised"] == "ValueError",
                        context_rejected=context["raised"] == "ValueError",
                        mutation_rejected=write["raised"] == "ValueError",
                        bytes_unchanged=path.read_text() == payload,
                        exception_types=[read["raised"], context["raised"], write["raised"]])
        expected = dict(read_rejected=True, context_rejected=True, mutation_rejected=True,
                        bytes_unchanged=True, exception_types=["ValueError"] * 3)
        record(name, expected, observed, observed == expected, "memory", "hardening")


def deletion_memory(position):
    with tempfile.TemporaryDirectory(prefix="synthetic-memory-") as folder:
        root = Path(folder)
        first = cli.remember(root, "Synthetic old preference", "synthetic:1", "project:A", "explicit")
        middle = cli.remember(root, "Synthetic revised preference", "synthetic:2", "project:A", "explicit", first["id"])
        latest = cli.remember(root, "Synthetic current preference", "synthetic:3", "project:A", "explicit", middle["id"])
        other = cli.remember(root, "Synthetic other scope", "synthetic:4", "project:B", "explicit")
        selected = (first, middle, latest)[position]
        with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
            code = cli.main(["--memory-dir", str(root), "forget", selected["id"]])
        stored = (root / "memory.json").read_text()
        graph = json.dumps(cli.graph(root))
        current = [e["text"] for e in cli.context(root, "", "project:A")]
        observed = dict(code=code, scope_A=current,
                        scope_B=[e["text"] for e in cli.context(root, "", "project:B")],
                        deleted_id_absent=selected["id"] not in stored and selected["id"] not in graph,
                        deleted_text_absent=selected["text"] not in stored and selected["text"] not in graph)
        expected = dict(code=0, scope_A=[] if position == 2 else [latest["text"]],
                        scope_B=[other["text"]], deleted_id_absent=True, deleted_text_absent=True)
        record("normal_delete_chain_position_" + str(position), expected, observed,
               observed == expected, "memory")


def dangling_memory():
    entries = [memory_entry("old", superseded_by="absent-new"),
               memory_entry("new", supersedes="absent-old"),
               memory_entry("tombstone", superseded_by="deleted-correction"),
               memory_entry("other", "project:B")]
    with tempfile.TemporaryDirectory(prefix="synthetic-memory-") as folder:
        root = Path(folder)
        payload = json.dumps(entries)
        (root / "memory.json").write_text(payload)
        observed = dict(read_count=len(cli.read_memory(root)),
                        active_A=[e["id"] for e in cli.context(root, "", "project:A")],
                        active_B=[e["id"] for e in cli.context(root, "", "project:B")],
                        unchanged=(root / "memory.json").read_text() == payload)
        expected = dict(read_count=4, active_A=["new"], active_B=["other"], unchanged=True)
        record("absent_correction_references_preserve_deleted_history", expected, observed,
               observed == expected, "memory")


def marker_collision_memory():
    entries = [memory_entry("old", superseded_by="deleted-correction"),
               memory_entry("deleted-correction")]
    with tempfile.TemporaryDirectory(prefix="synthetic-memory-") as folder:
        root = Path(folder)
        (root / "memory.json").write_text(json.dumps(entries))
        observed = dict(read_count=len(cli.read_memory(root)),
                        active=[e["id"] for e in cli.context(root, "", "project:A")])
        expected = dict(read_count=2, active=["deleted-correction"])
        record("deleted_history_marker_preserves_unrelated_live_identifier", expected, observed,
               observed == expected, "memory")


def cross_scope_correction():
    with tempfile.TemporaryDirectory(prefix="synthetic-memory-") as folder:
        root = Path(folder)
        first = cli.remember(root, "Synthetic old preference", "synthetic:1", "project:A", "explicit")
        original = (root / "memory.json").read_bytes()
        result = outcome(lambda: cli.remember(root, "Synthetic new preference", "synthetic:2", "project:B", "explicit", first["id"]))
        observed = dict(raised=result["raised"], unchanged=(root / "memory.json").read_bytes() == original)
        expected = dict(raised="ValueError", unchanged=True)
        record("normal_correction_cannot_move_across_scopes", expected, observed,
               observed == expected, "memory")


def verification_case(name, evidence, checks, expected_verdict, expected_gap=None):
    out = verify("Synthetic claim", evidence, checks)
    observed = dict(verdict=out["verdict"], gap_present=expected_gap in gaps(out) if expected_gap else not out["gaps"])
    expected = dict(verdict=expected_verdict, gap_present=True)
    record(name, expected, observed, observed == expected, "verification")


def verification_serializer():
    class Override(VerificationResult):
        def to_dict(self):
            return dict(verdict="passed", summary="forged summary", evidence_ids=["unknown"], name="forged", status="forged")
    out = verify("Synthetic claim", [ev("a")], [
        CallableVerifier("check", lambda claim, evidence: Override("failed", "Synthetic check failed.", ("a",)))])
    fields = ("name", "status", "verdict", "summary", "evidence_ids")
    observed = dict(verdict=out["verdict"],
                    check={key: out["checks"][0][key] for key in fields}, gaps=gaps(out))
    expected = dict(verdict="failed", check=dict(name="check", status="ok", verdict="failed",
                    summary="Synthetic check failed.", evidence_ids=["a"]), gaps=[])
    record("subclass_serializer_cannot_replace_checked_verifier_result", expected, observed,
           observed == expected, "verification", "hardening")


def diagnostic_retention():
    checks = [CallableVerifier("check" + str(i), lambda claim, evidence:
                              VerificationResult("passed", "S" * 6_000, ("a",))) for i in range(5)]
    out = verify("Synthetic claim", [ev("a")], checks)
    lengths = [len(check["summary"]) for check in out["checks"]]
    observed = dict(verdict=out["verdict"], checks=len(out["checks"]), summary_lengths=lengths,
                    total_summary_chars=sum(lengths), refs=[check["evidence_ids"] for check in out["checks"]])
    satisfied = (out["verdict"] == "passed" and len(out["checks"]) == 5
                 and max(lengths) <= 2_000 and sum(lengths) <= 8_000
                 and all(check["evidence_ids"] == ["a"] for check in out["checks"]))
    record("default_verifier_diagnostics_have_bounded_retained_size", dict(verdict="passed", checks=5,
           max_summary_chars=2_000, max_total_summary_chars=8_000, refs_preserved=True), observed,
           satisfied, "verification", "new-retention-bound-via-shared-signature")


for callback in [subclass_retrieval, ordinary_retrieval, dedup_retrieval, scope_retrieval,
                 failure_retrieval, sanitization_retrieval, conflict_retrieval,
                 truncated_retrieval, prior_truncation, metadata_retrieval, corpus_retrieval]:
    run(callback.__name__, callback, "retrieval")

malformed = [
    ("memory_rejects_present_self_correction", [memory_entry("a", supersedes="a", superseded_by="a")]),
    ("memory_rejects_present_cross_scope_correction", [memory_entry("a", superseded_by="b"), memory_entry("b", "project:B", supersedes="a")]),
    ("memory_rejects_present_nonreciprocal_correction", [memory_entry("a", superseded_by="b"), memory_entry("b")]),
    ("memory_rejects_present_reciprocal_cycle", [memory_entry("a", superseded_by="b", supersedes="b"), memory_entry("b", supersedes="a", superseded_by="a")]),
    ("memory_duplicate_ids_remain_rejected", [memory_entry("a"), memory_entry("a")]),
]
for name, entries in malformed:
    run(name, lambda name=name, entries=entries: malformed_memory(name, entries), "memory")
for position in range(3):
    run("delete_" + str(position), lambda position=position: deletion_memory(position), "memory")
for callback in [dangling_memory, marker_collision_memory, cross_scope_correction]:
    run(callback.__name__, callback, "memory")

check = lambda verdict, refs=("a",): CallableVerifier(verdict + str(refs), lambda claim, evidence: VerificationResult(verdict, "Synthetic diagnostic.", refs))
verification_cases = [
    ("ordinary_verification_pass", [ev("a")], [check("passed")], "passed", None),
    ("verification_failure_cannot_be_outvoted", [ev("a")], [check("passed"), check("failed")], "failed", None),
    ("verification_unknown_reference_is_inconclusive", [ev("a")], [check("passed", ("absent",))], "inconclusive", "invalid_evidence_reference"),
    ("verification_truncated_support_is_inconclusive", [ev("a", "part", original_chars=100, truncated=True)], [check("passed")], "inconclusive", "truncated_evidence"),
    ("verification_no_checks_is_inconclusive", [ev("a")], [], "inconclusive", "no_verifiers"),
]
for args in verification_cases:
    run(args[0], lambda args=args: verification_case(*args), "verification")

def failure_verification():
    def fail(claim, evidence):
        raise RuntimeError("synthetic-secret-should-not-leak")
    out = verify("Synthetic claim", [ev("a")], [CallableVerifier("broken", fail)])
    observed = dict(verdict=out["verdict"], gap="verifier_failed" in gaps(out),
                    leaked="synthetic-secret-should-not-leak" in json.dumps(out))
    expected = dict(verdict="inconclusive", gap=True, leaked=False)
    record("verification_callback_failure_and_error_redaction", expected, observed,
           observed == expected, "verification")

for callback in [failure_verification, verification_serializer, diagnostic_retention]:
    run(callback.__name__, callback, "verification")

output_path = options.output or Path(tempfile.mkdtemp(prefix="no-mistakes-comparison-")) / "observations.json"
output = dict(snapshot=str(snapshot), probe_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
              shared_api_policy="Same unmodified probe file and shared signatures; no candidate-only named arguments.",
              capabilities=dict(verify_parameters=list(inspect.signature(verify).parameters),
                                candidate_only_verify_parameters_are_not_scored=True),
              observations=observations)
with output_path.open("x", encoding="utf-8") as stream:
    stream.write(json.dumps(output, indent=2) + "\n")
print(json.dumps(dict(output=str(output_path), observations=len(observations),
                     criteria_satisfied=sum(row["satisfied"] for row in observations))))
