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
class ContextBudget:
    """Bound retained evidence, not model tokens or provider memory/network use.

    Text limits count Unicode characters. Metadata is kept exactly or rejected;
    clipping source references would change provenance. Callbacks still need their
    own timeouts, response-size limits, and access controls.
    """

    max_excerpt_chars: int = 2_000
    max_text_chars: int = 8_000
    max_metadata_chars: int = 1_024
    max_candidates_per_provider: int = 50

    def __post_init__(self) -> None:
        for field in ("max_excerpt_chars", "max_text_chars", "max_metadata_chars",
                      "max_candidates_per_provider"):
            if type(getattr(self, field)) is not int or getattr(self, field) < 1:
                raise ValueError(f"{field} must be a positive integer")


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
    original_chars: int | None = None
    truncated: bool = False

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
        if self.original_chars is None:
            object.__setattr__(self, "original_chars", len(self.text))
        if type(self.original_chars) is not int or self.original_chars < len(self.text):
            raise ValueError("original_chars must be an integer at least as large as the text")
        if type(self.truncated) is not bool:
            raise ValueError("truncated must be a bool")
        if self.truncated != (self.original_chars > len(self.text)):
            raise ValueError("truncated must match original_chars and the retained text length")

    def to_dict(self) -> dict[str, Any]:
        return {"id": self.id, "text": self.text, "source": self.source,
                "scope": self.scope, "provider": self.provider, "score": self.score,
                "original_chars": self.original_chars, "truncated": self.truncated}

    @classmethod
    def from_dict(cls, value: Mapping[str, Any]) -> Evidence:
        """Read the documented fields; provider-specific extra metadata is ignored."""
        if not isinstance(value, Mapping):
            raise ValueError("evidence must be an object")
        if "original_chars" in value and type(value["original_chars"]) is not int:
            raise ValueError("original_chars must be an integer")
        try:
            return cls(id=value["id"], text=value["text"], source=value["source"],
                       scope=value["scope"], provider=value.get("provider"),
                       score=value.get("score"), original_chars=value.get("original_chars"),
                       truncated=value.get("truncated", False))
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


def _retain_excerpts(envelope: dict[str, Any], selected: Sequence[Evidence],
                     budget: ContextBudget) -> dict[str, Any]:
    """Clip only after full-text conflict checks; never claim complete coverage."""
    usage = envelope["context_budget"]
    clipped_providers = set()
    statuses = {status["name"]: status for status in envelope["providers"]}
    exhausted = False
    for item in selected:
        remaining = budget.max_text_chars - usage["retained_text_chars"]
        if not remaining:
            usage["omitted_items"] += 1
            exhausted = True
            continue
        text = item.text[:min(budget.max_excerpt_chars, remaining)]
        if not text.strip():
            # Do not emit an unusable Evidence record containing only whitespace.
            usage["omitted_items"] += 1
            envelope["gaps"].append({"provider": item.provider, "reason": "empty_excerpt"})
            continue
        truncated = item.truncated or len(text) < len(item.text)
        envelope["evidence"].append(replace(item, text=text, truncated=truncated).to_dict())
        statuses[item.provider]["accepted"] += 1
        usage["retained_text_chars"] += len(text)
        if truncated:
            usage["truncated_items"] += 1
            if item.provider not in clipped_providers:
                envelope["gaps"].append({"provider": item.provider, "reason": "excerpt_truncated"})
                clipped_providers.add(item.provider)
    if exhausted:
        envelope["gaps"].append({"provider": None, "reason": "text_budget_exhausted"})
    return envelope


def retrieve(request: RetrievalRequest, retrievers: Sequence[Retriever],
             sanitize_query: Callable[[str], str] | None = None, *,
             budget: ContextBudget | None = None) -> dict[str, Any]:
    """Collect scoped evidence, isolating failures and keeping provider order.

    Round-robin merging respects each provider's own ordering without comparing
    unrelated scoring scales. The final limit applies across all providers.
    Query text is deliberately absent from the returned envelope. All evidence
    fields remain untrusted data, including strings that look like instructions.
    Character budgets reduce retained context; they are not injection detection,
    automatic PII redaction, token limits, or a sandbox for callback code.
    """
    if not isinstance(request, RetrievalRequest):
        raise ValueError("request must be a RetrievalRequest")
    if sanitize_query is not None and not callable(sanitize_query):
        raise ValueError("sanitize_query must be callable")
    if budget is None:
        budget = ContextBudget()
    if not isinstance(budget, ContextBudget):
        raise ValueError("budget must be a ContextBudget")
    if len(request.scope) > budget.max_metadata_chars:
        raise ValueError("scope exceeds max_metadata_chars")
    providers = tuple(retrievers)
    names = []
    for provider in providers:
        _nonempty(provider.name, "provider name")
        if len(provider.name) > budget.max_metadata_chars:
            raise ValueError("provider name exceeds max_metadata_chars")
        if not isinstance(provider.external, bool) or not callable(provider.retrieve):
            raise ValueError("retrievers must declare external and implement retrieve")
        names.append(provider.name)
    if len(names) != len(set(names)):
        raise ValueError("retriever names must be unique")

    envelope: dict[str, Any] = {
        "kind": "retrieval", "scope": request.scope, "limit": request.limit,
        "retrieved_at": datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z"),
        "evidence": [], "providers": [], "gaps": [], "verified": False,
        "trust": "untrusted",
        "context_budget": {
            "max_excerpt_chars": budget.max_excerpt_chars,
            "max_text_chars": budget.max_text_chars,
            "max_metadata_chars": budget.max_metadata_chars,
            "max_candidates_per_provider": budget.max_candidates_per_provider,
            "retained_text_chars": 0, "truncated_items": 0, "omitted_items": 0,
        },
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
        if request.limit > budget.max_candidates_per_provider:
            provider_request = replace(request, limit=budget.max_candidates_per_provider)
            gap("candidate_limit")
        if provider.external:
            if sanitize_query is None:
                gap("sanitization_required", "blocked")
                continue
            try:
                cleaned = sanitize_query(request.query)
                provider_request = replace(provider_request, query=cleaned)
            except Exception:
                gap("sanitization_failed", "blocked")
                continue
        try:
            result = provider.retrieve(provider_request)
        except Exception:
            gap("retriever_failed", "error")
            continue
        try:
            if not isinstance(result, Sequence) or isinstance(result, (str, bytes)):
                gap("invalid_result", "error")
                continue
            status["returned"] = len(result)
            limited = result[:budget.max_candidates_per_provider]
            if (len(result) > budget.max_candidates_per_provider
                    and request.limit <= budget.max_candidates_per_provider):
                gap("candidate_limit")
            if any(not isinstance(item, Evidence) for item in limited):
                gap("invalid_result", "error")
                continue
        except Exception:
            gap("invalid_result", "error")
            continue
        bounded = [item for item in limited
                   if all(len(getattr(item, field)) <= budget.max_metadata_chars
                          for field in ("id", "source", "scope"))
                   and (item.provider is None or len(item.provider) <= budget.max_metadata_chars)]
        if len(bounded) != len(limited):
            gap("metadata_limit")
        candidates = [replace(item, provider=provider.name) for item in bounded
                      if item.scope == request.scope]
        if len(candidates) != len(bounded):
            gap("scope_mismatch")
        if not candidates:
            gap("empty_result", "empty")
        for item in candidates:
            key = (item.source, item.id, item.scope)
            previous = observed.setdefault(key, item)
            if (previous.text, previous.original_chars, previous.truncated) != (
                    item.text, item.original_chars, item.truncated):
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
    selected: list[Evidence] = []
    for position in range(max(map(len, batches), default=0)):
        for index, batch in enumerate(batches):
            if position >= len(batch):
                continue
            item = batch[position]
            key = (item.source, item.id, item.scope)
            if key in seen:
                continue
            seen.add(key)
            selected.append(item)
            if len(selected) == request.limit:
                return _retain_excerpts(envelope, selected, budget)
    if not providers:
        envelope["gaps"].append({"provider": None, "reason": "no_retrievers"})
    return _retain_excerpts(envelope, selected, budget)


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

    Unknown/ambiguous evidence references, passes relying on truncated evidence,
    and checker errors are inconclusive.
    A passed result describes these callbacks, not a universal accuracy guarantee.
    """
    _nonempty(claim, "claim")
    items = tuple(evidence)
    if any(not isinstance(item, Evidence) for item in items):
        raise ValueError("evidence must contain Evidence objects")
    available_ids = {item.id for item in items}
    truncated_ids = {item.id for item in items if item.truncated}
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
            if result.verdict == "passed" and truncated_ids.intersection(result.evidence_ids):
                result = VerificationResult(
                    "inconclusive", "Supporting evidence is truncated; inspect its original source.",
                    result.evidence_ids,
                )
                envelope["gaps"].append({"verifier": checker.name, "reason": "truncated_evidence"})
            envelope["checks"].append({"name": checker.name, "status": "ok", **result.to_dict()})
    verdicts = [check["verdict"] for check in envelope["checks"]]
    if "failed" in verdicts:
        envelope["verdict"] = "failed"
    elif verdicts and all(verdict == "passed" for verdict in verdicts):
        envelope["verdict"] = "passed"
    if not checkers:
        envelope["gaps"].append({"verifier": None, "reason": "no_verifiers"})
    return envelope
