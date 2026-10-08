from dataclasses import FrozenInstanceError
import json
from pathlib import Path
import tempfile
import unittest

from no_mistakes.integrations import (
    CallableRetriever, CallableVerifier, Evidence, LocalCorpusRetriever,
    RetrievalRequest, VerificationBudget, VerificationResult, retrieve, verify,
)


def item(item_id="one", text="Python retries are configurable.", source="docs:1", scope="demo", **kwargs):
    return Evidence(item_id, text, source, scope, **kwargs)


def local_retriever(name, callback):
    return CallableRetriever(name, callback, external=False)


class RetrievalTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.corpus = Path(self.temp.name) / "corpus.json"

    def write_corpus(self, documents):
        self.corpus.write_text(json.dumps(documents), encoding="utf-8")

    def test_local_keyword_ranking_and_scope(self):
        self.write_corpus([
            item("weak", "Python supports many libraries.").to_dict(),
            item("secret", "Private Python retries", scope="other").to_dict(),
            item("best", "Python retries are configurable.").to_dict(),
            item("unrelated", "Green apples.").to_dict(),
        ])
        result = retrieve(RetrievalRequest("PYTHON retries", "demo", 2),
                          [LocalCorpusRetriever(self.corpus)])
        self.assertEqual([doc["id"] for doc in result["evidence"]], ["best", "weak"])
        self.assertEqual(result["evidence"][0]["score"], 1.0)
        self.assertEqual(result["evidence"][0]["provider"], "local-corpus")
        self.assertFalse(result["verified"])
        self.assertNotIn("query", result)
        self.assertNotIn("Private", json.dumps(result))
        self.assertTrue(result["retrieved_at"].endswith("Z"))
        json.dumps(result, allow_nan=False)

    def test_round_robin_deduplication_and_global_limit(self):
        first = local_retriever("a", lambda request: [
            item(score=-1000), item(), item("two", source="docs:2", score=-500)])
        second = local_retriever("b", lambda request: [
            item(provider="invented", score=100000), item("three", source="docs:3")])
        result = retrieve(RetrievalRequest("Python", "demo", 3), [first, second])
        self.assertEqual([doc["id"] for doc in result["evidence"]], ["one", "two", "three"])
        self.assertEqual([doc["provider"] for doc in result["evidence"]], ["a", "a", "b"])
        self.assertEqual([provider["accepted"] for provider in result["providers"]], [2, 1])
        self.assertEqual(len(retrieve(RetrievalRequest("Python", "demo", 1),
                                     [first, second])["evidence"]), 1)

    def test_same_id_different_source_is_preserved(self):
        result = retrieve(RetrievalRequest("Python", "demo"), [
            local_retriever("a", lambda request: [item(source="a")]),
            local_retriever("b", lambda request: [item(source="b")]),
        ])
        self.assertEqual([doc["source"] for doc in result["evidence"]], ["a", "b"])

    def test_conflicting_duplicates_are_excluded_and_reported(self):
        for retrievers in ([
            local_retriever("a", lambda request: [item(text="Retries are safe."), item("other")]),
            local_retriever("b", lambda request: [item(text="Retries are unsafe.")]),
        ], [local_retriever("a", lambda request: [
            item(text="Retries are safe."), item(text="Retries are unsafe."), item("other")])]):
            result = retrieve(RetrievalRequest("Retries", "demo"), retrievers)
            self.assertEqual([doc["id"] for doc in result["evidence"]], ["other"])
            self.assertEqual({gap["reason"] for gap in result["gaps"]}, {"evidence_conflict"})
            self.assertNotIn("Retries are safe.", json.dumps(result))
            self.assertNotIn("Retries are unsafe.", json.dumps(result))

    def test_external_query_requires_sanitization_and_local_keeps_original(self):
        calls = []

        def capture(label):
            def callback(request):
                calls.append((label, request))
                return [item(source=label)]
            return callback

        local = local_retriever("local", capture("local"))
        remote = CallableRetriever("remote", capture("remote"), external=True)
        request = RetrievalRequest("private@example.test Python", "demo", 2)
        blocked = retrieve(request, [remote])
        self.assertEqual(calls, [])
        self.assertEqual(blocked["providers"][0]["status"], "blocked")
        self.assertEqual(blocked["gaps"][0]["reason"], "sanitization_required")

        def sanitize(query):
            calls.append(("sanitize", query))
            return "[EMAIL] Python"

        result = retrieve(request, [remote, local], sanitize_query=sanitize)
        self.assertEqual(calls[0], ("sanitize", request.query))
        self.assertEqual(calls[1][0], "remote")
        self.assertEqual(calls[1][1], RetrievalRequest("[EMAIL] Python", "demo", 2))
        self.assertEqual(calls[2][1], request)
        self.assertEqual(len(result["evidence"]), 2)
        self.assertNotIn("private@example.test", json.dumps(result))

    def test_failed_or_empty_sanitizer_never_invokes_external(self):
        calls = []

        def forbidden(request):
            calls.append(request)
            return [item()]

        def explode(query):
            raise ValueError("secret-sanitizer-content")

        for sanitize in (explode, lambda query: " ", lambda query: None):
            with self.subTest(sanitize=sanitize):
                calls.clear()
                result = retrieve(RetrievalRequest("private", "demo"),
                                  [CallableRetriever("remote", forbidden, external=True)], sanitize)
                self.assertEqual(calls, [])
                self.assertEqual(result["gaps"][0]["reason"], "sanitization_failed")
                self.assertNotIn("secret-sanitizer-content", json.dumps(result))

    def test_partial_failure_invalid_results_and_wrong_scope_are_explicit(self):
        def explode(request):
            raise RuntimeError("token=super-private-and-secret")

        result = retrieve(RetrievalRequest("Python", "demo"), [
            local_retriever("broken", explode),
            local_retriever("wrong-type", lambda request: [{"text": "unvalidated secret"}]),
            local_retriever("other-scope", lambda request: [item(text="TOP SECRET", scope="other")]),
            local_retriever("good", lambda request: [item()]),
        ])
        self.assertEqual([doc["provider"] for doc in result["evidence"]], ["good"])
        self.assertEqual([provider["status"] for provider in result["providers"]],
                         ["error", "error", "empty", "ok"])
        self.assertEqual({gap["reason"] for gap in result["gaps"]},
                         {"retriever_failed", "invalid_result", "scope_mismatch", "empty_result"})
        for forbidden in ("token=", "super-private", "TOP SECRET", "unvalidated secret"):
            self.assertNotIn(forbidden, json.dumps(result))

    def test_empty_and_broken_corpus(self):
        self.write_corpus([item(text="Unrelated apples").to_dict()])
        result = retrieve(RetrievalRequest("Python", "demo"), [LocalCorpusRetriever(self.corpus)])
        self.assertEqual(result["evidence"], [])
        self.assertEqual(result["providers"][0]["status"], "empty")
        self.corpus.write_text("invalid private JSON", encoding="utf-8")
        broken = retrieve(RetrievalRequest("Python", "demo"), [LocalCorpusRetriever(self.corpus)])
        self.assertEqual(broken["providers"][0]["status"], "error")
        self.assertNotIn("invalid private JSON", json.dumps(broken))
        self.assertEqual(retrieve(RetrievalRequest("Python", "demo"), [])["gaps"],
                         [{"provider": None, "reason": "no_retrievers"}])

    def test_validation_and_json_safe_evidence(self):
        for query, scope, limit in (("", "demo", 5), (" ", "demo", 5),
                                    ("x", "", 5), ("x", "demo", 0),
                                    ("x", "demo", -1), ("x", "demo", 1.5),
                                    ("x", "demo", True)):
            with self.assertRaises(ValueError):
                RetrievalRequest(query, scope, limit)
        for score in (float("nan"), float("inf"), True, "high"):
            with self.assertRaises(ValueError):
                item(score=score)
        self.assertEqual(Evidence.from_dict(item().to_dict()), item())
        for invalid in ({}, None, {**item().to_dict(), "id": ""}):
            with self.assertRaises(ValueError):
                Evidence.from_dict(invalid)
        with self.assertRaises(ValueError):
            retrieve(RetrievalRequest("x", "demo"), [
                local_retriever("same", lambda request: []),
                local_retriever("same", lambda request: []),
            ])

    def test_callable_retriever_defaults_to_external(self):
        calls = []

        def forbidden(request):
            calls.append(request)
            return [item()]

        result = retrieve(RetrievalRequest("private", "demo"), [CallableRetriever("default", forbidden)])
        self.assertEqual(calls, [])
        self.assertEqual(result["gaps"][0]["reason"], "sanitization_required")

    def test_evidence_preserves_valid_truncation_metadata(self):
        full = item(text="Full excerpt")
        self.assertEqual(full.original_chars, len(full.text))
        self.assertIs(full.truncated, False)
        clipped = item(text="Missing caveat", original_chars=40, truncated=True)
        self.assertEqual(Evidence.from_dict(clipped.to_dict()), clipped)
        self.assertEqual(clipped.to_dict()["original_chars"], 40)
        self.assertIs(clipped.to_dict()["truncated"], True)

    def test_inconsistent_or_invalid_truncation_metadata_is_rejected(self):
        record = item(text="Fact").to_dict()
        for metadata in (
            {"original_chars": None}, {"original_chars": True},
            {"original_chars": 4.5}, {"original_chars": "4"},
            {"original_chars": 0}, {"original_chars": 3},
            {"original_chars": 5, "truncated": False},
            {"original_chars": 4, "truncated": True},
            {"truncated": 1}, {"truncated": "false"},
        ):
            with self.subTest(metadata=metadata):
                with self.assertRaises(ValueError):
                    Evidence.from_dict({**record, **metadata})
        with self.assertRaises(ValueError):
            Evidence.from_dict({"id": "one", "text": "Fact", "source": "docs:1",
                                "scope": "demo", "truncated": True})


class VerificationTests(unittest.TestCase):
    def checker(self, name, verdict, refs=("one",)):
        return CallableVerifier(name, lambda claim, evidence:
                                VerificationResult(verdict, f"{name} check complete.", refs))

    def test_failure_cannot_be_outvoted(self):
        result = verify("Retries work", [item()], [
            self.checker("tests", "passed"), self.checker("facts", "failed"),
            self.checker("schema", "passed"),
        ])
        self.assertEqual(result["verdict"], "failed")
        self.assertEqual([check["verdict"] for check in result["checks"]],
                         ["passed", "failed", "passed"])
        json.dumps(result, allow_nan=False)

    def test_inconclusive_and_missing_checkers(self):
        result = verify("Retries work", [item()], [
            self.checker("tests", "passed"), self.checker("freshness", "inconclusive"),
        ])
        self.assertEqual(result["verdict"], "inconclusive")
        self.assertEqual(verify("Retries work", [item()], [])["verdict"], "inconclusive")
        self.assertEqual(verify("Retries work", [item()], [self.checker("tests", "passed")])["verdict"],
                         "passed")

    def test_missing_required_checker_cannot_disappear_from_coverage(self):
        result = verify("Release requires unit and package checks", [item()],
                        [self.checker("unit", "passed")],
                        required_verifiers=("unit", "package"))
        self.assertEqual(result["verdict"], "inconclusive")
        self.assertEqual([check["name"] for check in result["checks"]], ["unit"])
        self.assertEqual(result["checks"][0]["verdict"], "passed")
        self.assertEqual(result["gaps"],
                         [{"verifier": "package", "reason": "required_verifier_missing"}])

    def test_required_checker_coverage_does_not_hide_failures_or_errors(self):
        failed = verify("Release checks", [item()], [self.checker("unit", "failed")],
                        required_verifiers=("unit", "package"))
        self.assertEqual(failed["verdict"], "failed")
        errored = verify("Release checks", [item()],
                         [CallableVerifier("package", lambda claim, evidence: None),
                          self.checker("unit", "passed")],
                         required_verifiers=("unit", "package"))
        self.assertEqual(errored["verdict"], "inconclusive")
        self.assertEqual(errored["gaps"][0]["reason"], "invalid_result")
        self.assertFalse(any(gap["reason"] == "required_verifier_missing"
                             for gap in errored["gaps"]))

    def test_complete_required_coverage_and_optional_checks(self):
        result = verify("Release checks", [item()],
                        [self.checker("package", "passed"),
                         self.checker("unit", "passed"),
                         self.checker("advisory", "passed")],
                        required_verifiers=["unit", "package"])
        self.assertEqual(result["verdict"], "passed")
        self.assertEqual(result["gaps"], [])
        missing = verify("Release checks", [], [], required_verifiers=["package"])
        self.assertEqual(missing["verdict"], "inconclusive")
        self.assertEqual({gap["reason"] for gap in missing["gaps"]},
                         {"required_verifier_missing", "no_verifiers"})
        for required in (None, (), []):
            with self.subTest(required=required):
                legacy = verify("Release checks", [item()],
                                [self.checker("unit", "passed")],
                                required_verifiers=required)
                self.assertEqual(legacy["verdict"], "passed")

    def test_invalid_required_names_are_rejected_before_callbacks(self):
        calls = []
        checker = CallableVerifier("unit", lambda claim, evidence: calls.append(claim))
        for required in ("unit", b"unit", True, {"unit"}, ["unit", "unit"], [""], [1]):
            with self.subTest(required=required), self.assertRaises(ValueError):
                verify("Release checks", [item()], [checker], required_verifiers=required)
        self.assertEqual(calls, [])

    def test_unknown_or_ambiguous_provenance_prevents_pass(self):
        for evidence, refs in (([item()], ("invented",)), ([], ("one",))):
            result = verify("Retries work", evidence, [self.checker("facts", "passed", refs)])
            self.assertEqual(result["verdict"], "inconclusive")
            self.assertEqual(result["gaps"][0]["reason"], "invalid_evidence_reference")
            self.assertEqual(result["checks"][0]["evidence_ids"], [])
            self.assertNotIn("invented", json.dumps(result))
        with self.assertRaises(ValueError):
            verify("Retries work", [item(), item(source="other-source")],
                   [self.checker("facts", "passed")])

    def test_checker_errors_and_malformed_results_do_not_leak_or_pass(self):
        def explode(claim, evidence):
            raise RuntimeError("token=never-show-this")

        result = verify("Retries work", [item()], [
            CallableVerifier("broken", explode),
            CallableVerifier("truthy", lambda claim, evidence: True),
            CallableVerifier("string", lambda claim, evidence: "passed"),
            self.checker("tests", "passed"),
        ])
        self.assertEqual(result["verdict"], "inconclusive")
        self.assertEqual([gap["reason"] for gap in result["gaps"]],
                         ["verifier_failed", "invalid_result", "invalid_result"])
        self.assertNotIn("never-show-this", json.dumps(result))
        failed = verify("Retries work", [item()], [
            CallableVerifier("broken", explode), self.checker("tests", "failed"),
        ])
        self.assertEqual(failed["verdict"], "failed")

    def test_pass_referencing_truncated_evidence_is_inconclusive(self):
        evidence = [item(text="Allowed.", original_chars=38, truncated=True)]
        result = verify("Public deployment is allowed", evidence,
                        [self.checker("terms", "passed")])
        self.assertEqual(result["verdict"], "inconclusive")
        self.assertEqual(result["checks"][0]["verdict"], "inconclusive")
        self.assertEqual(result["checks"][0]["evidence_ids"], ["one"])
        self.assertEqual(result["gaps"], [{"verifier": "terms", "reason": "truncated_evidence"}])

    def test_truncation_does_not_hide_failure_or_block_independent_checks(self):
        evidence = [item(text="Allowed.", original_chars=38, truncated=True)]
        failed = verify("Public deployment is allowed", evidence,
                        [self.checker("terms", "failed"), self.checker("calculation", "passed", ())])
        self.assertEqual(failed["verdict"], "failed")
        independent = verify("17 * 43 = 731", evidence,
                             [self.checker("calculation", "passed", ())])
        self.assertEqual(independent["verdict"], "passed")
        self.assertEqual(independent["gaps"], [])
        other = verify("Full excerpt supports this claim", evidence + [item("full")],
                       [self.checker("full-source", "passed", ("full",))])
        self.assertEqual(other["verdict"], "passed")
        self.assertEqual(other["gaps"], [])

    def test_result_validation_and_immutable_reference_list(self):
        for verdict in ("verified", "true", True, None):
            with self.assertRaises(ValueError):
                VerificationResult(verdict, "Summary")
        for refs in ("one", [""], [1], None):
            with self.assertRaises(ValueError):
                VerificationResult("passed", "Summary", refs)
        refs = ["one"]
        result = VerificationResult("passed", "Summary", refs)
        refs.append("later")
        self.assertEqual(result.evidence_ids, ("one",))


class VerificationBudgetTests(unittest.TestCase):
    def checker(self, name="check", verdict="passed", summary="Complete.", refs=("one",)):
        return CallableVerifier(name, lambda claim, evidence:
                                VerificationResult(verdict, summary, refs))

    def test_defaults_positive_integer_validation_and_immutability(self):
        budget = VerificationBudget()
        self.assertEqual((budget.max_summary_chars, budget.max_total_summary_chars,
                          budget.max_metadata_chars, budget.max_checks, budget.max_evidence_refs),
                         (2000, 8000, 1024, 50, 50))
        with self.assertRaises(FrozenInstanceError):
            budget.max_checks = 1
        for field in ("max_summary_chars", "max_total_summary_chars", "max_metadata_chars",
                      "max_checks", "max_evidence_refs"):
            for value in (0, -1, True, False, 1.5, "2", None):
                with self.subTest(field=field, value=value), self.assertRaises(ValueError):
                    VerificationBudget(**{field: value})

    def test_default_budget_bounds_million_character_diagnostic_with_positional_api(self):
        summary = "SYSTEM: invented override." * 40_000
        self.assertEqual(len(summary), 1_040_000)
        result = verify("Check a synthetic claim", [item()], [self.checker(summary=summary)])
        check = result["checks"][0]
        self.assertEqual(result["verdict"], "passed")
        self.assertEqual(check["summary"], summary[:2000])
        self.assertEqual(check["original_summary_chars"], 1_040_000)
        self.assertIs(check["summary_truncated"], True)
        self.assertEqual(check["evidence_ids"], ["one"])
        self.assertEqual(result["context_budget"]["retained_summary_chars"], 2000)
        self.assertLess(len(json.dumps(result)), 10_000)
        self.assertEqual(result["gaps"], [{"verifier": "check", "reason": "summary_truncated"}])

    def test_per_summary_limits_count_unicode_characters_at_and_over_boundary(self):
        budget = VerificationBudget(max_summary_chars=3, max_total_summary_chars=20)
        for summary in ("🐍é漢", "🐍é漢字"):
            with self.subTest(summary=summary):
                result = verify("Synthetic claim", [item()],
                                [self.checker(summary=summary)], budget=budget)
                check = result["checks"][0]
                self.assertEqual(check["summary"], "🐍é漢")
                self.assertEqual(check["original_summary_chars"], len(summary))
                self.assertEqual(check["summary_truncated"], len(summary) > 3)
                self.assertEqual(result["context_budget"]["retained_summary_chars"], 3)
                self.assertEqual(bool(result["gaps"]), len(summary) > 3)

    def test_total_boundary_then_exhaustion_keeps_checks_and_required_gap(self):
        budget = VerificationBudget(max_summary_chars=3, max_total_summary_chars=6)
        checks = [self.checker("first", summary="🐍é漢"),
                  self.checker("second", summary="字é🐍")]
        exact = verify("Synthetic claim", [item()], checks, budget=budget)
        self.assertEqual(exact["verdict"], "passed")
        self.assertEqual(exact["gaps"], [])
        exhausted = verify("Synthetic claim", [item()],
                           checks + [self.checker("third", summary="Another diagnostic")],
                           required_verifiers=("first", "second", "third", "missing"),
                           budget=budget)
        self.assertEqual([check["summary"] for check in exhausted["checks"]],
                         ["🐍é漢", "字é🐍", ""])
        self.assertEqual([check["name"] for check in exhausted["checks"]],
                         ["first", "second", "third"])
        self.assertEqual(exhausted["verdict"], "inconclusive")
        self.assertEqual(exhausted["context_budget"]["retained_summary_chars"], 6)
        self.assertEqual(exhausted["context_budget"]["truncated_summaries"], 1)
        self.assertEqual(exhausted["context_budget"]["omitted_summaries"], 1)
        self.assertEqual(exhausted["gaps"], [
            {"verifier": "missing", "reason": "required_verifier_missing"},
            {"verifier": "third", "reason": "summary_truncated"},
            {"verifier": None, "reason": "summary_budget_exhausted"},
        ])

    def test_partial_and_omitted_diagnostics_never_hide_failure(self):
        result = verify("Synthetic claim", [item()], [
            self.checker("first", summary="🐍é漢字"),
            self.checker("second", summary="Four", verdict="inconclusive"),
            self.checker("third", summary="Failure details", verdict="failed"),
            self.checker("fourth", summary="More failure details", verdict="failed"),
        ], budget=VerificationBudget(max_summary_chars=4, max_total_summary_chars=5))
        self.assertEqual([check["summary"] for check in result["checks"]],
                         ["🐍é漢字", "F", "", ""])
        self.assertEqual([check["verdict"] for check in result["checks"]],
                         ["passed", "inconclusive", "failed", "failed"])
        self.assertEqual(result["verdict"], "failed")
        self.assertEqual(result["context_budget"]["truncated_summaries"], 3)
        self.assertEqual(result["context_budget"]["omitted_summaries"], 2)
        self.assertEqual(sum(gap["reason"] == "summary_budget_exhausted"
                             for gap in result["gaps"]), 1)

    def test_summary_clipping_preserves_each_verdict_but_not_clipped_evidence_pass(self):
        budget = VerificationBudget(max_summary_chars=1)
        for verdict in ("passed", "failed", "inconclusive"):
            with self.subTest(verdict=verdict):
                result = verify("Synthetic claim", [item()],
                                [self.checker(verdict=verdict)], budget=budget)
                self.assertEqual(result["verdict"], verdict)
                self.assertEqual(result["checks"][0]["verdict"], verdict)
        clipped_evidence = item(text="Allowed.", original_chars=38, truncated=True)
        result = verify("Synthetic claim", [clipped_evidence], [self.checker()], budget=budget)
        self.assertEqual(result["verdict"], "inconclusive")
        self.assertEqual({gap["reason"] for gap in result["gaps"]},
                         {"truncated_evidence", "summary_truncated"})

    def test_budget_and_preflight_limits_reject_before_any_callback_without_echo(self):
        calls = []

        def capture(claim, evidence):
            calls.append(claim)
            return VerificationResult("passed", "Complete.", ())

        good = CallableVerifier("valid", capture)
        secret = "private" * 150
        cases = [
            {"budget": "private-invalid-budget"},
            {"evidence": [item(item_id=secret)]},
            {"verifiers": [good, CallableVerifier(secret, capture)]},
            {"required_verifiers": [secret]},
            {"verifiers": [good, CallableVerifier("other", capture)],
             "budget": VerificationBudget(max_checks=1)},
            {"required_verifiers": ["valid", "other"],
             "budget": VerificationBudget(max_checks=1)},
        ]
        for case in cases:
            arguments = {"claim": "Synthetic claim", "evidence": [item()], "verifiers": [good]}
            arguments.update(case)
            with self.subTest(case=list(case)), self.assertRaises(ValueError) as error:
                verify(**arguments)
            self.assertNotIn("private", str(error.exception))
        self.assertEqual(calls, [])

    def test_metadata_and_check_count_exact_boundaries_preserve_provenance(self):
        result = verify("Synthetic claim", [item(item_id="12345")],
                        [self.checker("first", refs=("12345",)),
                         self.checker("other", refs=("12345",))],
                        required_verifiers=("first", "other"),
                        budget=VerificationBudget(max_metadata_chars=5, max_checks=2))
        self.assertEqual(result["verdict"], "passed")
        self.assertEqual([check["name"] for check in result["checks"]], ["first", "other"])
        self.assertEqual([check["evidence_ids"] for check in result["checks"]],
                         [["12345"], ["12345"]])
        self.assertEqual(result["context_budget"]["max_metadata_chars"], 5)
        self.assertEqual(result["context_budget"]["max_checks"], 2)

    def test_reference_overflow_preserves_valid_failure_and_never_clips_refs(self):
        budget = VerificationBudget(max_evidence_refs=1, max_summary_chars=5)
        for verdict in ("passed", "failed", "inconclusive"):
            with self.subTest(verdict=verdict):
                result = verify("Synthetic claim", [item()],
                                [self.checker(verdict=verdict, summary="private-diagnostic",
                                              refs=("one", "one"))], budget=budget)
                check = result["checks"][0]
                self.assertEqual(check["verdict"], "failed" if verdict == "failed" else "inconclusive")
                self.assertEqual(result["verdict"], check["verdict"])
                self.assertEqual(check["status"], "error")
                self.assertEqual(check["evidence_ids"], [])
                self.assertNotIn("private", json.dumps(result))
                self.assertEqual({gap["reason"] for gap in result["gaps"]},
                                 {"evidence_reference_limit", "summary_truncated"})
        exact = verify("Synthetic claim", [item()], [self.checker()], budget=budget)
        self.assertEqual(exact["checks"][0]["evidence_ids"], ["one"])
        unknown = verify("Synthetic claim", [item()],
                         [self.checker(verdict="failed", refs=("one", "private-unknown"))],
                         budget=budget)
        self.assertEqual(unknown["verdict"], "inconclusive")
        self.assertEqual(unknown["gaps"][0]["reason"], "invalid_evidence_reference")
        self.assertNotIn("private-unknown", json.dumps(unknown))

    def test_malformed_callback_objects_and_errors_remain_generic_when_budget_exhausts(self):
        malformed = VerificationResult("passed", "private-invalid-summary", ())
        object.__setattr__(malformed, "evidence_ids", [None])

        def explode(claim, evidence):
            raise RuntimeError("private-error-token")

        result = verify("Synthetic claim", [item()], [
            self.checker("first", summary="x", verdict="failed"),
            CallableVerifier("malformed", lambda claim, evidence: malformed),
            CallableVerifier("broken", explode),
        ], budget=VerificationBudget(max_total_summary_chars=1))
        self.assertEqual(result["verdict"], "failed")
        self.assertEqual([check["summary"] for check in result["checks"]], ["x", "", ""])
        self.assertEqual([check["status"] for check in result["checks"]], ["ok", "error", "error"])
        self.assertTrue({"invalid_result", "verifier_failed"}.issubset(
            {gap["reason"] for gap in result["gaps"]}))
        self.assertNotIn("private", json.dumps(result))

    def test_preflight_names_are_stable_and_callback_serializers_cannot_expand_output(self):
        class CustomResult(VerificationResult):
            def to_dict(self):
                return {"summary": "private-serializer" * 1000}

        checker = None

        def callback(claim, evidence):
            checker.name = "private-mutated-name" * 1000
            return CustomResult("passed", "Complete.", ("one",))

        checker = CallableVerifier("stable", callback)
        result = verify("Synthetic claim", [item()], [checker])
        self.assertEqual(result["checks"][0]["name"], "stable")
        self.assertEqual(result["checks"][0]["summary"], "Complete.")
        self.assertEqual(result["verdict"], "passed")
        self.assertNotIn("private", json.dumps(result))


if __name__ == "__main__":
    unittest.main()
