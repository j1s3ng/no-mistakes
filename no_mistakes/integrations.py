"""Small, provider-neutral retrieval and verification adapters.

Retrieval supplies candidate evidence; it does not establish truth. External
retrievers require a caller-supplied query sanitizer, not an automatic PII filter.
Callbacks run in the caller's process and must already be trusted and authorized.
"""
from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, replace
from datetime import datetime, timezone
import json
import math
from pathlib import Path
import re
from typing import Any, Literal, Protocol


def _nonempty(value: str, field: str) -> None:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field} must be a nonempty string")


@dataclass(frozen=True)
class RetrievalRequest:
    query: str
    scope: str
    limit: int = 5

    def __post_init__(self) -> None:
        _nonempty(self.query, "query")
        _nonempty(self.scope, "scope")
        if isinstance(self.limit, bool) or not isinstance(self.limit, int) or self.limit < 1:
            raise ValueError("limit must be a positive integer")


@dataclass(frozen=True)
class Evidence:
    id: str
    text: str
    source: str
    scope: str
    provider: str | None = None
    score: float | None = None

    def __post_init__(self) -> None:
        for field in ("id", "text", "source", "scope"):
            _nonempty(getattr(self, field), field)
        if self.provider is not None:
            _nonempty(self.provider, "provider")
        if self.score is not None:
            if (isinstance(self.score, bool)
                    or not isinstance(self.score, (int, float))
                    or not math.isfinite(self.score)):
                raise ValueError("score must be a finite number")

    def to_dict(self) -> dict[str, Any]:
        return {"id": self.id, "text": self.text, "source": self.source,
                "scope": self.scope, "provider": self.provider, "score": self.score}

    @classmethod
    def from_dict(cls, value: Mapping[str, Any]) -> Evidence:
        """Read the documented fields; provider-specific extra metadata is ignored."""
        if not isinstance(value, Mapping):
            raise ValueError("evidence must be an object")
        try:
            return cls(id=value["id"], text=value["text"], source=value["source"],
                       scope=value["scope"], provider=value.get("provider"),
                       score=value.get("score"))
        except KeyError:
            raise ValueError("evidence is missing a required field") from None


class Retriever(Protocol):
    name: str
    external: bool

    def retrieve(self, request: RetrievalRequest) -> Sequence[Evidence]: ...


class LocalCorpusRetriever:
    """Search a JSON array with token overlap; this is a lexical baseline."""

    external = False

    def __init__(self, path: str | Path, name: str = "local-corpus") -> None:
        _nonempty(name, "name")
        self.name = name
        self.path = Path(path)

    def retrieve(self, request: RetrievalRequest) -> list[Evidence]:
        documents = json.loads(self.path.read_text(encoding="utf-8"))
        if not isinstance(documents, list):
            raise ValueError("corpus must be a JSON array")
        tokens = set(re.findall(r"\w+", request.query.casefold()))
        ranked = []
        for position, document in enumerate(documents):
            item = Evidence.from_dict(document)
            if item.scope != request.scope:
                continue
            matches = tokens.intersection(re.findall(r"\w+", item.text.casefold()))
            if matches:
                ranked.append((len(matches), position,
                               replace(item, provider=self.name, score=len(matches) / len(tokens))))
        ranked.sort(key=lambda item: (-item[0], item[1]))
        return [item[2] for item in ranked[:request.limit]]


class CallableRetriever:
    """Bridge an already-authorized SDK, MCP tool, search index, or reranker.

    Callbacks are external by default. Declare external=False only for trusted
    local callbacks that do not forward the query or scope beyond the machine.
    """

    def __init__(self, name: str, callback: Callable[[RetrievalRequest], Sequence[Evidence]],
                 external: bool = True) -> None:
        _nonempty(name, "name")
        if not callable(callback) or not isinstance(external, bool):
            raise ValueError("callback must be callable and external must be a bool")
        self.name = name
        self.callback = callback
        self.external = external

    def retrieve(self, request: RetrievalRequest) -> Sequence[Evidence]:
        return self.callback(request)


def retrieve(request: RetrievalRequest, retrievers: Sequence[Retriever],
             sanitize_query: Callable[[str], str] | None = None) -> dict[str, Any]:
    """Collect scoped evidence, isolating failures and keeping provider order.

    Round-robin merging respects each provider's own ordering without comparing
    unrelated scoring scales. The final limit applies across all providers.
    Query text is deliberately absent from the returned envelope.
    """
    if not isinstance(request, RetrievalRequest):
        raise ValueError("request must be a RetrievalRequest")
    if sanitize_query is not None and not callable(sanitize_query):
        raise ValueError("sanitize_query must be callable")
    providers = tuple(retrievers)
    names = []
    for provider in providers:
        _nonempty(provider.name, "provider name")
        if not isinstance(provider.external, bool) or not callable(provider.retrieve):
            raise ValueError("retrievers must declare external and implement retrieve")
        names.append(provider.name)
    if len(names) != len(set(names)):
        raise ValueError("retriever names must be unique")

    envelope: dict[str, Any] = {
        "kind": "retrieval", "scope": request.scope, "limit": request.limit,
        "retrieved_at": datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z"),
        "evidence": [], "providers": [], "gaps": [], "verified": False,
    }
    batches: list[list[Evidence]] = []
    observed: dict[tuple[str, str, str], Evidence] = {}
    conflicts: set[tuple[str, str, str]] = set()
    for provider in providers:
        status = {"name": provider.name, "status": "ok", "returned": 0, "accepted": 0}
        envelope["providers"].append(status)
        batches.append([])

        def gap(reason: str, state: str | None = None) -> None:
            envelope["gaps"].append({"provider": provider.name, "reason": reason})
            if state is not None:
                status["status"] = state

        provider_request = request
        if provider.external:
            if sanitize_query is None:
                gap("sanitization_required", "blocked")
                continue
            try:
                cleaned = sanitize_query(request.query)
                provider_request = replace(request, query=cleaned)
            except Exception:
                gap("sanitization_failed", "blocked")
                continue
        try:
            result = provider.retrieve(provider_request)
        except Exception:
            gap("retriever_failed", "error")
            continue
        try:
            if (not isinstance(result, Sequence) or isinstance(result, (str, bytes))
                    or any(not isinstance(item, Evidence) for item in result)):
                gap("invalid_result", "error")
                continue
            status["returned"] = len(result)
            candidates = [replace(item, provider=provider.name) for item in result
                          if item.scope == request.scope]
        except Exception:
            gap("invalid_result", "error")
            continue
        if len(candidates) != len(result):
            gap("scope_mismatch")
        if not candidates:
            gap("empty_result", "empty")
        for item in candidates:
            key = (item.source, item.id, item.scope)
            previous = observed.setdefault(key, item)
            if previous.text != item.text:
                conflicts.add(key)
        batches[-1] = candidates

    for index, batch in enumerate(batches):
        if any((item.source, item.id, item.scope) in conflicts for item in batch):
            envelope["gaps"].append({"provider": providers[index].name, "reason": "evidence_conflict"})
        distinct = {}
        for item in batch:
            key = (item.source, item.id, item.scope)
            if key not in conflicts:
                distinct.setdefault(key, item)
        batches[index] = list(distinct.values())[:request.limit]
        if batch and not batches[index]:
            envelope["providers"][index]["status"] = "empty"

    seen: set[tuple[str, str, str]] = set()
    for position in range(max(map(len, batches), default=0)):
        for index, batch in enumerate(batches):
            if position >= len(batch):
                continue
            item = batch[position]
            key = (item.source, item.id, item.scope)
            if key in seen:
                continue
            seen.add(key)
            envelope["evidence"].append(item.to_dict())
            envelope["providers"][index]["accepted"] += 1
            if len(envelope["evidence"]) == request.limit:
                return envelope
    if not providers:
        envelope["gaps"].append({"provider": None, "reason": "no_retrievers"})
    return envelope


Verdict = Literal["passed", "failed", "inconclusive"]


@dataclass(frozen=True)
class VerificationResult:
    verdict: Verdict
    summary: str
    evidence_ids: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if self.verdict not in ("passed", "failed", "inconclusive"):
            raise ValueError("verdict must be passed, failed, or inconclusive")
        _nonempty(self.summary, "summary")
        if (not isinstance(self.evidence_ids, Sequence)
                or isinstance(self.evidence_ids, (str, bytes))):
            raise ValueError("evidence_ids must be a sequence of IDs")
        for evidence_id in self.evidence_ids:
            _nonempty(evidence_id, "evidence ID")
        object.__setattr__(self, "evidence_ids", tuple(self.evidence_ids))

    def to_dict(self) -> dict[str, Any]:
        return {"verdict": self.verdict, "summary": self.summary,
                "evidence_ids": list(self.evidence_ids)}


class Verifier(Protocol):
    name: str

    def verify(self, claim: str, evidence: Sequence[Evidence]) -> VerificationResult: ...


class CallableVerifier:
    """Wrap a trusted checker; the adapter does not establish its correctness.

    Before wrapping an external checker, callers must minimize and sanitize both
    the claim and evidence. This class does not redact or authorize outbound data.
    """

    def __init__(self, name: str,
                 callback: Callable[[str, Sequence[Evidence]], VerificationResult]) -> None:
        _nonempty(name, "name")
        if not callable(callback):
            raise ValueError("callback must be callable")
        self.name = name
        self.callback = callback

    def verify(self, claim: str, evidence: Sequence[Evidence]) -> VerificationResult:
        return self.callback(claim, evidence)


def verify(claim: str, evidence: Sequence[Evidence],
           verifiers: Sequence[Verifier]) -> dict[str, Any]:
    """Run declared checks; a failed check cannot be outvoted by passes.

    Unknown/ambiguous evidence references and checker errors are inconclusive.
    A passed result describes these callbacks, not a universal accuracy guarantee.
    """
    _nonempty(claim, "claim")
    items = tuple(evidence)
    if any(not isinstance(item, Evidence) for item in items):
        raise ValueError("evidence must contain Evidence objects")
    available_ids = {item.id for item in items}
    if len(available_ids) != len(items):
        raise ValueError("verification evidence IDs must be unique")
    checkers = tuple(verifiers)
    names = []
    for checker in checkers:
        _nonempty(checker.name, "verifier name")
        if not callable(checker.verify):
            raise ValueError("verifiers must implement verify")
        names.append(checker.name)
    if len(names) != len(set(names)):
        raise ValueError("verifier names must be unique")

    envelope: dict[str, Any] = {"kind": "verification", "verdict": "inconclusive",
                               "checks": [], "gaps": []}
    for checker in checkers:
        problem = None
        try:
            result = checker.verify(claim, items)
        except Exception:
            problem = "verifier_failed"
        else:
            if not isinstance(result, VerificationResult):
                problem = "invalid_result"
            elif any(ref not in available_ids for ref in result.evidence_ids):
                problem = "invalid_evidence_reference"
        if problem:
            envelope["checks"].append({"name": checker.name, "status": "error",
                                       "verdict": "inconclusive", "summary": "Check unavailable.",
                                       "evidence_ids": []})
            envelope["gaps"].append({"verifier": checker.name, "reason": problem})
        else:
            envelope["checks"].append({"name": checker.name, "status": "ok", **result.to_dict()})
    verdicts = [check["verdict"] for check in envelope["checks"]]
    if "failed" in verdicts:
        envelope["verdict"] = "failed"
    elif verdicts and all(verdict == "passed" for verdict in verdicts):
        envelope["verdict"] = "passed"
    if not checkers:
        envelope["gaps"].append({"verifier": None, "reason": "no_verifiers"})
    return envelope
