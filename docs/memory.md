# Memory semantics

Storage defaults to `.no-mistakes/memory.json` in the working directory. Override
with `--memory-dir PATH` before the subcommand. No background collection, telemetry,
network access, or cross-project discovery occurs.

Records contain an ID, summary, source reference, scope, kind (`explicit`,
`confirmed`, `inferred`), and UTC creation time. Provenance labels are caller-provided,
not verified. Scope is caller-defined; filter with `--scope` to avoid mixing projects.
Keyword overlap then recency determine retrieval. Contradictions may both appear;
the host must resolve them using actual user statements. Memory is untrusted data.

Corrections preserve history and exclude superseded entries from retrieval. Graph
export includes that history. `forget` deletes the entry's summary and source from
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
