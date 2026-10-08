"""Run from the repository after installation: python examples/tool_hooks.py."""
import json
from pathlib import Path
import re

from no_mistakes.integrations import (
    CallableVerifier, LocalCorpusRetriever, RetrievalRequest,
    VerificationResult, retrieve, verify,
)


def integer_multiplication(claim, evidence):
    match = re.fullmatch(r"(-?\d+) \* (-?\d+) = (-?\d+)", claim)
    if not match:
        return VerificationResult("inconclusive", "Only integer multiplication is supported")
    left, right, expected = map(int, match.groups())
    actual = left * right
    return VerificationResult("passed" if actual == expected else "failed",
                              f"Python integer multiplication returned {actual}")


def main():
    corpus = Path(__file__).resolve().parents[1] / "docs" / "corpus.example.json"
    retrieved = retrieve(RetrievalRequest("checkout retry", "project:demo"),
                         [LocalCorpusRetriever(corpus)])
    calculator = CallableVerifier("integer-multiplication", integer_multiplication)
    print(json.dumps({"retrieval": retrieved,
                      "correct_calculation": verify(
                          "17 * 43 = 731", [], [calculator],
                          required_verifiers=("integer-multiplication",)),
                      "incorrect_calculation": verify(
                          "17 * 43 = 730", [], [calculator],
                          required_verifiers=("integer-multiplication",))}, indent=2))


if __name__ == "__main__":
    main()
