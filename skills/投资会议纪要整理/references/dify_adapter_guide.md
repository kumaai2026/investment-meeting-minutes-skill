# Dify Adapter Guide

Use this file only when the meeting-minutes skill is called from a Dify workflow or the local Dify Skill Agent plugin. The base skill is the source of truth for meeting-note content and Markdown format.

## Boundary

- Dify is an orchestration adapter for upload, extraction/transcription, review gates, archive confirmation, export, and sync.
- Dify-specific fields, review URLs, draft IDs, workflow status, and sync status belong in workflow metadata or API responses, not in the final note body.
- Dify nodes must not rewrite the generated Markdown structure after the skill returns.
- The final note is the human-confirmed Markdown, not the model draft.

## Required Gates

The Dify chain is:

1. Upload files, meeting title, meeting date, meeting type, and meeting series.
2. Extract document text or run SenseVoice transcription.
3. Create an initial-review draft through the review bridge.
4. Wait for human initial review and confirmation.
5. Re-run the workflow with `input_reviewed=true`.
6. Invoke the base meeting-minutes skill with `meeting_type` as a formatting parameter.
7. Create a second-review draft through the review bridge.
8. Wait for human final-note confirmation.
9. Generate any post-review structured table or archive preview required by the local review flow.
10. Wait for explicit archive confirmation.
11. Export Markdown + Word, sync the final note to the knowledge base, and trigger Google Drive sync when configured.

Do not export, sync, or archive an initial transcript, an unreviewed model draft, or a final draft that has not passed archive confirmation.

## Meeting Type Formatting

Always invoke the base meeting-minutes skill. Do not dispatch to another skill by meeting type.

Use `meeting_type` only to choose output formatting:

- `多人复盘会`: default; use for pre-market discussion, review meetings, morning/weekly/regular meetings, and multi-speaker investment sharing.
- `上市公司交流`: use only for a single-company special meeting focused on that company's operations, business, earnings, orders, capacity, management Q&A, and risks.
- `专家交流`: use only for expert Q&A sessions, whether focused on one company or on an industry/sector.

If the type is unknown, custom, or empty, normalize it to `多人复盘会`.

## Input Fields

Dify may pass:

- `combined_text`
- `text_reference`
- `sensevoice_transcript`
- `sensevoice_timestamp_index`
- `meeting_title`
- `meeting_date`
- `meeting_type`
- `meeting_series`
- `input_reviewed`

If `input_reviewed` is missing or false, return only a minimal initial-review placeholder and do not run the final meeting-note formatting step.

When the Dify Skill Agent receives upstream text fields, treat them as the current session's valid meeting materials. Do not ask the user to upload or paste the same materials again.

## Subagent Use

Use Subagents inside the Dify path only when the runtime explicitly supports them. If Subagent execution is unavailable, continue with the single-agent workflow and preserve the same review gates.

Allowed Subagent intermediate outputs:

- transcript-quality notes
- `发言整理` candidate blocks
- target/company/code candidate lists
- doubtful-item verification notes
- source-conflict summaries
- omission and distortion findings

These outputs are inputs to the final writer. They must not be copied directly into the final note as workflow logs or debug fields.

## Doubtful-Item Verification Prompt

Use the stable verification prompt in `references/evidence_policy.md` for every non-person doubtful item before final-note formatting. Dify may implement it as one dedicated prompt node or as part of the Skill Agent prompt, but the required inputs and output fields must stay aligned with that canonical prompt.

## Returned Fields

The Dify workflow should expose draft/review plumbing separately from the note body:

- `result_markdown`
- `review_url`
- `drafts_url`
- `history_url`
- `draft_id`

The final human-readable Markdown must not contain these process fields.

## Archive And Sync

- Raw-file archiving may call `http://host.docker.internal:8766/archive-inputs`.
- The archive bridge should return raw-file sync status when background sync is attempted.
- The review bridge handles `/draft`, `/review`, `/confirm-input`, `/confirm-archive`, `/history`, `/external-sources`, `/target-query`, `/sync-status`, and `/health`.
- Archive confirmation is the only point where final Markdown + Word export, knowledge-base sync, and Google Drive sync are allowed.

## Failure Policy

- If the Skill Agent output lacks `## 一、发言整理`, reject the post-agent draft. `## 二、存疑与待确认` is required only when real doubtful content exists.
- If transcription, review bridge, export, knowledge sync, or Google Drive sync fails, report the failing step explicitly.
- Keep local confirmed Markdown/Word outputs if downstream sync fails.
- Never delete local files to recover from a workflow or sync error.
