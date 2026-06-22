# MAS Sidecar Artifact Contract

本文件定义 Skill-first MAS 的内部 sidecar。Sidecar 用于调试、审计和人工确认，不进入最终 Markdown/Word 正文。

## 公共字段

每个 sidecar artifact 必须包含：

```json
{
  "artifact_type": "source_profile",
  "artifact_version": "1.0",
  "source_id": "meeting-2026-06-22-demo",
  "source_hash": "sha256:...",
  "created_by_role": "intake",
  "input_refs": [],
  "status": "draft",
  "warnings": [],
  "requires_human_review": false
}
```

字段规则：
- `artifact_type`: 必须是本文件列出的类型。
- `artifact_version`: 当前固定为 `1.0`。
- `source_id`: 同一会议的一组 sidecar 使用同一 source id。
- `source_hash`: 使用 `sha256:<hex>` 或 `unavailable:<reason>`。
- `created_by_role`: 生成角色，例如 `intake`、`transcript_agent`、`target_attribution_agent`。
- `input_refs`: 上游 artifact 或 source material 引用。
- `status`: `draft`、`needs_review`、`confirmed`、`rejected`、`skipped` 之一。
- `warnings`: 字符串数组。
- `requires_human_review`: 布尔值。

## source_profile

用途：定义本次会议的输入边界。

必需字段：
- `input_mode`: `audio_only` / `document_only` / `audio_plus_document`
- `files`
- `meeting_type_candidate`
- `has_audio`
- `has_document`
- `has_timestamp`
- `known_speakers`
- `known_targets`
- `sensitive_terms`
- `processing_notes`

## transcript_audit

用途：审计音频转写和文稿冲突。仅 `audio_only` 或 `audio_plus_document` 必需。

必需字段：
- `input_mode`
- `speaker_boundary_issues`
- `timestamp_anchors`
- `low_confidence_terms`
- `asr_conflicts`
- `audio_document_conflicts`
- `suspected_entities`

## segmentation_plan

用途：规划逐发言人正文结构。

必需字段：
- `meeting_type`
- `speech_order`
- `segments`
- `split_required`
- `merge_forbidden`

每个 `segments` 项应包含：
- `segment_id`
- `speaker`
- `source_refs`
- `topic_hint`
- `target_hint`
- `reason_for_split`

## target_attribution_ledger

用途：记录段落内标的归因。

必需字段：
- `segments`

每个 `segments` 项必须包含：
- `segment_id`
- `primary_target`
- `mentioned_targets`
- `recommendation_target`
- `target_roles`
- `title_requirement`
- `attribution_confidence`
- `attribution_notes`

`target_roles` 至少区分：
- `primary`
- `recommendation`
- `comparison`
- `customer`
- `supplier`
- `competitor`
- `upstream`
- `downstream`
- `industry_background`
- `incidental`
- `uncertain`

## evidence_ledger

用途：记录实体和高风险 claim 的证据状态。

必需字段：
- `claims`

每个 `claims` 项必须包含：
- `claim_id`
- `claim_type`
- `claim_text`
- `source_refs`
- `source_evidence`
- `local_reference_evidence`
- `external_verification_path`
- `evidence_status`
- `final_handling`

`evidence_status` 必须是：
- `confirmed`
- `candidate_only`
- `conflicting`
- `unverified`
- `not_found`
- `not_applicable`

## suspect_confirmation

用途：列出需要人工确认的内容。

必需字段：
- `items`

每个 `items` 项必须包含：
- `item_id`
- `source_refs`
- `original_expression`
- `current_judgment`
- `uncertainty_reason`
- `candidate_values`
- `context`
- `suggested_confirmation_path`
- `final_note_handling`

## draft_review_report

用途：红队复核草稿。

必需字段：
- `findings`
- `checked_dimensions`
- `go_status`

每个 `findings` 项必须包含：
- `finding_id`
- `severity`
- `segment_id`
- `issue_type`
- `description`
- `recommended_fix`
- `status`

## qa_report

用途：记录脚本校验结果。

必需字段：
- `checks`
- `go_status`
- `no_go_reasons`

每个 `checks` 项必须包含：
- `check_name`
- `command`
- `ok`
- `errors`
- `warnings`

## 终稿隔离

最终 Markdown/Word 不得包含任何 sidecar artifact 的 JSON、字段名、工具日志或内部路径。
