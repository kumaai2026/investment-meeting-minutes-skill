# Internal Artifact Privacy Policy

Only two internal artifacts are authoritative:

- `analysis_ledger.json`
- `qa_report.json`

They are internal review artifacts, not final notes and not RAG documents.

## Storage

Internal artifacts should live under:

```text
.meeting-minutes-internal/
```

They must not be written into:

- Formal Markdown or Word output directories.
- Dify knowledge-base sync payloads.
- Google Drive sync output.
- Sanitizer RAG outputs.
- Public examples containing real meeting material.

## Git And Sync Excludes

Repositories and sync scripts should exclude:

```text
**/.meeting-minutes-internal/**
**/*_analysis_ledger.json
**/*_qa_report.json
```

Do not change unrelated sync behavior only to support this policy.

## Forbidden Keys And Values

Validators must inspect both keys and recursive string values. Internal artifacts and public fixtures must not contain:

- `/Users/`
- `C:\`
- `file://`
- review URLs
- draft ID URLs
- `token=`
- `api_key`
- `Authorization`
- `Bearer`
- `cookie`
- localhost review endpoints

Use placeholders such as `<repo-root>`, `<workflow-root>`, `<redacted-note.md>`, and `<redacted-note.docx>` in reusable reports and fixtures.

## Final Note Isolation

Final Markdown/Word may contain only reader-facing meeting content, metadata, corrected near-original text, and the ambiguity table when real uncertainty exists.

Final notes must not contain `analysis_ledger`, `qa_report`, JSON field names, tool logs, local paths, review URLs, draft IDs, or internal reviewer status.
