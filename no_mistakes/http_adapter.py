"""Opt-in JSON retrieval over HTTPS; no model calls or automatic PII detection."""
from dataclasses import dataclass
import json
import math
import os
from urllib.parse import urlsplit
from urllib.request import HTTPRedirectHandler, Request, build_opener

from .integrations import Evidence, RetrievalRequest


class _NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


@dataclass
class JsonHttpRetriever:
    """POST a scoped query to an explicitly chosen endpoint returning evidence JSON.

    Use through integrations.retrieve(), which requires a query sanitizer because
    external=True. Backend access control and privacy review remain the caller's job.
    """
    name: str
    endpoint: str
    token_env: str | None = None
    timeout: float = 10.0
    max_response_bytes: int = 1_000_000
    allow_local_http: bool = False
    external = True

    def __post_init__(self):
        if not isinstance(self.name, str) or not self.name.strip():
            raise ValueError("An adapter name is required")
        try:
            parts = urlsplit(self.endpoint)
            hostname = parts.hostname
        except (TypeError, ValueError):
            raise ValueError("Invalid endpoint URL") from None
        local = (self.allow_local_http and parts.scheme == "http"
                 and hostname in ("localhost", "127.0.0.1", "::1"))
        if (not hostname or (parts.scheme != "https" and not local)
                or parts.username is not None or parts.password is not None
                or parts.query or parts.fragment):
            raise ValueError("Use HTTPS without URL credentials, query, or fragment")
        # Validate the port without putting the endpoint in an error message.
        try:
            parts.port
        except ValueError:
            raise ValueError("Invalid endpoint port") from None
        if (isinstance(self.timeout, bool) or not isinstance(self.timeout, (int, float))
                or not math.isfinite(self.timeout) or self.timeout <= 0):
            raise ValueError("timeout must be finite and positive")
        if (type(self.max_response_bytes) is not int or self.max_response_bytes < 1):
            raise ValueError("max_response_bytes must be a positive integer")
        if self.token_env is not None and (not isinstance(self.token_env, str)
                                           or not self.token_env.strip()):
            raise ValueError("token_env must be a nonempty environment variable name")

    def retrieve(self, request: RetrievalRequest):
        headers = {"Content-Type": "application/json", "Accept": "application/json"}
        if self.token_env:
            token = os.environ.get(self.token_env)
            if not token or any(char.isspace() for char in token):
                raise ValueError("Bearer token is missing or invalid")
            headers["Authorization"] = "Bearer " + token
        body = json.dumps({"query": request.query, "scope": request.scope,
                           "limit": request.limit}).encode("utf-8")
        req = Request(self.endpoint, data=body, headers=headers, method="POST")
        # Redirects are refused so credentials and queries stay at the chosen URL.
        with build_opener(_NoRedirect()).open(req, timeout=self.timeout) as response:
            payload = response.read(self.max_response_bytes + 1)
        if len(payload) > self.max_response_bytes:
            raise ValueError("Retrieval response exceeds size limit")
        result = json.loads(payload)
        if not isinstance(result, dict) or not isinstance(result.get("evidence"), list):
            raise ValueError("Expected an object with an evidence array")
        return [Evidence.from_dict(item) for item in result["evidence"]]
