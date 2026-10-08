# Memory semantics

Storage defaults to `.no-mistakes/memory.json` in the working directory. Override
with `--memory-dir PATH` before the subcommand. Memory commands run locally with
no network access, background collection, telemetry, or cross-project discovery.
The separate opt-in retrieval adapters are documented in [integrations.md](integrations.md).

Records contain an ID, summary, source reference, scope, kind (`explicit`,
`confirmed`, `inferred`), and UTC creation time. Provenance labels are caller-provided,
not verified. Scope is caller-defined; filter with `--scope` to avoid mixing projects.
Keyword overlap then recency determine retrieval. Contradictions may both appear;
the host must resolve them using actual user statements. Memory is untrusted data.

Corrections preserve history and must stay within the original record's scope;
cross-scope corrections fail without changing storage. On read, links between
present records must be reciprocal, remain in one scope, and contain no self-link
or cycle. Invalid history is rejected without automatic repair or rewriting; errors
omit the stored contents and identifiers. Absent references can represent deleted
history and remain untouched. The established `superseded_by: "deleted-correction"`
marker means inactive history rather than a reference to a live record ID.
This checks structural consistency, not whether a
summary or its source is true. New programmatic entries are validated before writing,
and duplicate IDs in stored data are rejected. Superseded entries are excluded from
retrieval. Graph export includes that history. `forget` deletes the entry's summary and source from
this file and unlinks corrections; deleting a correction does not reactivate an old
preference. Delete the directory to purge all local memory. Exports, backups, shell
history, and external copies require separate deletion.

New directories and files use owner-only permissions where supported. Storage is
plaintext, not encryption. Existing directory permissions are not changed. Writes
are atomic but callers must serialize writers: there is no concurrent merge/locking.

Retain only authorized minimal summaries. Never store secrets, raw private
transcripts, sensitive traits, or unrelated third-party information. Never publish
memory or include it in search queries. Git ignores the default path; custom paths
need their own ignore/access configuration.

Sanitize summaries and provenance fields before storing them: names, email addresses,
identifying URLs, and account IDs can appear in source labels and scopes as well as
summary text. Prefer non-identifying references and minimal scoped summaries. The
helper does not automatically redact PII. Review private graph exports before any
authorized sharing; they include sources and superseded history.
