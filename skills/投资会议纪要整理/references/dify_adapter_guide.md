# Dify Adapter Guide

Use this file only when the meeting-minutes skill is called from a Dify workflow or the local Dify Skill Agent plugin. The base skill remains the source of truth for content rules and Markdown output format.

## Boundary

- Dify is an orchestration adapter, not an output-format owner.
- The selected type skill generates the Markdown body. Dify nodes must not rewrite the generated Markdown structure after the skill returns.
- The base skill defines shared rules; type skills define type-specific output shape.
- Dify-specific fields, review URLs, draft IDs, and sync status belong in workflow metadata or API responses, not in the final note body.

## Required Gates

The Dify chain is:

1. Upload files, meeting title, meeting date, meeting type, and meeting series.
2. Extract text or run SenseVoice/FunASR transcription.
3. Create a `pre_agent` draft through the review bridge.
4. Wait for human initial review and confirmation.
5. Re-run the Dify workflow with `input_reviewed=true`.
6. Invoke the selected type skill.
7. Create a `post_agent` draft through the review bridge.
8. Wait for human second review and final-note confirmation.
9. Generate post-review structured summary and target-table artifacts.
10. Wait for explicit archive confirmation.
11. Export Markdown + Word, sync the final note to the Dify knowledge base, and trigger Google Drive sync.

Do not export, sync, or archive an initial transcript, an unreviewed model draft, or a final draft that has not passed archive confirmation.

## Skill Dispatch

Map the selected meeting type to the local folder name:

| Dify meeting type | Skill folder |
| --- | --- |
| 多人复盘会 | 投资会议纪要-多人复盘会 |
| 上市公司交流 | 投资会议纪要-上市公司交流 |
| 专家交流 | 投资会议纪要-专家交流 |
| 其他 / custom | 投资会议纪要-其他 |

The `skill_name` passed to the Dify Skill Agent should be the local folder name, not only the frontmatter `name`.

## Input Fields

Dify may pass:

- `combined_text`
- `text_reference`
- `sensevoice_transcript`
- `sensevoice_timestamp_index`
- `meeting_title`
- `meeting_date`
- `meeting_type`
- `custom_meeting_type`
- `meeting_series`
- `input_reviewed`

If `input_reviewed` is missing or false, return only a minimal initial-review placeholder and do not run the meeting-note formatting step.

When the Dify Skill Agent receives the upstream text fields, treat them as the current session's valid meeting materials. Do not ask the user to upload or paste the same materials again.

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
- The archive bridge should return `google_drive_synced` and `google_drive_message` when raw-file background sync is attempted.
- The review bridge handles `/draft`, `/review`, `/confirm-input`, `/confirm-archive`, `/history`, `/external-sources`, `/target-query`, `/sync-status`, and `/health`.
- Archive confirmation is the only point where final Markdown + Word export, Dify knowledge-base sync, and Google Drive sync are allowed.

## Failure Policy

- If the Skill Agent output lacks `## 一、逐发言人原文整理`, reject the post-agent draft. `## 二、存疑与待确认` is required only when real doubtful content exists.
- If transcription, review bridge, export, Dify knowledge sync, or Google Drive sync fails, report the failing step explicitly.
- Keep local confirmed Markdown/Word outputs if downstream sync fails.
- Never delete local files to recover from a Dify or sync error.
