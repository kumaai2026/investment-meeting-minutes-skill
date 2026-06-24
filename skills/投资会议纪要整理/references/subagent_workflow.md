# Conditional Subagent Workflow

This skill package is Skill-first and contract-first with conditional Codex Subagents. It is not a full MAS framework and does not use LangGraph, CrewAI, AutoGen, or similar orchestration layers.

Main Orchestrator is the only writer of final Markdown, Word, archive, and sync artifacts. Subagents are read-only reviewers. Deterministic validators decide hard pass/fail status.

## Architecture

```text
Main Orchestrator
├─ Transcript Auditor Subagent
├─ Content Integrity Reviewer Subagent
│  ├─ pre_draft
│  └─ post_draft
├─ Main Orchestrator writes and revises the final draft
└─ Deterministic validators
```

## Input Flows

### audio_only and audio_plus_document

```text
source material
-> ASR
-> conditional Transcript Auditor
-> existing human initial review
-> Content Integrity Reviewer pre_draft
-> Main Orchestrator writes draft
-> Content Integrity Reviewer post_draft
-> script validators
-> existing human second review
-> export, archive, and sync
```

Unconfirmed ASR output must not be used as high-confidence target-attribution input before human initial review.

### document_only

```text
document text
-> existing input confirmation / human initial review
-> conditional Content Integrity Reviewer pre_draft
-> Main Orchestrator writes draft
-> Content Integrity Reviewer post_draft
-> script validators
-> human second review
-> export
```

## Trigger Rules

### Transcript Auditor

Explicitly spawn project-scoped `transcript_auditor`, wait for its structured result, merge the result into the internal `analysis_ledger`, then continue when any condition is true:

- `audio_only`.
- `audio_plus_document` with audio/document conflict.
- Speaker boundaries are unclear.
- Key entities, stock codes, numbers, units, or technical terms are low-confidence.
- Reliable time anchors are needed.

Use at most one Transcript Auditor thread per meeting.

### Content Integrity Reviewer pre_draft

Explicitly spawn project-scoped `content_integrity_reviewer` with `mode=pre_draft`, wait for its result, then let Main Orchestrator decide segmentation and headings when any condition is true:

- A semantic segment contains more than one target.
- The source contains recommendation, buy, sell, add, reduce, avoid, or other investment action.
- Main discussion object and action object may differ.
- Customers, suppliers, competitors, comparable companies, upstream/downstream entities, or background entities appear.
- Orders, capacity, price, profit, revenue, gross margin, valuation, market cap, or other high-risk facts appear.
- Meeting type is `多人复盘会`.
- A previous version misidentified recommendation targets.

Use at most one Content Integrity Reviewer thread per meeting. Do not spawn one reviewer per paragraph.

### Content Integrity Reviewer post_draft

After the draft exists, formal meeting minutes should by default explicitly spawn `content_integrity_reviewer` with `mode=post_draft` and wait for findings. Only Main Orchestrator may revise the draft.

Post-draft review may be skipped only for pure format conversion or when the user explicitly asks for a fast informal draft.

## Failure And Fallback

If a subagent spawn fails, times out, or returns invalid JSON:

- Do not claim the review passed.
- Low-risk tasks may fall back to single-agent processing.
- High-risk tasks set `requires_human_review=true`.
- Existing human confirmation gates are not skipped.
- Record failure in the internal QA report.
- Do not write failure details into the final note body.

See `subagent_failure_policy.md`.

## Dify Boundary

Dify remains an adapter for upload, extraction/transcription, human gates, type-skill invocation, archive confirmation, and sync.

Dify subagent execution is unverified; existing single-agent fallback remains authoritative.

Dify status values are limited to `PASS`, `FAIL`, and `UNVERIFIED`.

## Internal Artifacts

Only two internal artifacts are authoritative:

- `analysis_ledger.json`
- `qa_report.json`

They belong under `.meeting-minutes-internal/` or another explicitly internal directory and must not enter final Markdown, Word, Dify knowledge base, Google Drive sync output, or sanitized RAG output.
