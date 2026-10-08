import json
from pathlib import Path
import tempfile
import unittest

from no_mistakes.integrations import (
    CallableRetriever, CallableVerifier, Evidence, LocalCorpusRetriever,
    RetrievalRequest, VerificationResult, retrieve, verify,
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
        def forbidden(request):
            self.fail("external callback was invoked")

        def explode(query):
            raise ValueError("secret-sanitizer-content")

        for sanitize in (explode, lambda query: " ", lambda query: None):
            result = retrieve(RetrievalRequest("private", "demo"),
                              [CallableRetriever("remote", forbidden, external=True)], sanitize)
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
        def forbidden(request):
            self.fail("default external callback was invoked without sanitization")

        result = retrieve(RetrievalRequest("private", "demo"), [CallableRetriever("default", forbidden)])
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


if __name__ == "__main__":
    unittest.main()
