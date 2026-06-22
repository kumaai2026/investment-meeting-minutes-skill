#!/usr/bin/env python3
"""Validate Skill-first MAS sidecar artifacts and sample final notes."""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any

ARTIFACT_VERSION = "1.0"
COMMON_FIELDS = [
    "artifact_type",
    "artifact_version",
    "source_id",
    "source_hash",
    "created_by_role",
    "input_refs",
    "status",
    "warnings",
    "requires_human_review",
]
VALID_STATUSES = {"draft", "needs_review", "confirmed", "rejected", "skipped"}
VALID_ARTIFACT_TYPES = {
    "source_profile",
    "transcript_audit",
    "segmentation_plan",
    "target_attribution_ledger",
    "evidence_ledger",
    "suspect_confirmation",
    "draft_review_report",
    "qa_report",
    "internal_sidecar",
    "rag_sidecar",
}
VALID_EVIDENCE_STATUS = {
    "confirmed",
    "candidate_only",
    "conflicting",
    "unverified",
    "not_found",
    "not_applicable",
}
RAG_FORBIDDEN_KEYS = {
    "speaker_name",
    "speaker_identity",
    "speaker_affiliation",
    "speaker_style",
    "raw_source_path",
    "absolute_path",
    "review_url",
    "draft_id",
    "history_url",
    "api_key",
    "token",
    "cookie",
    "source_span",
    "raw_transcript",
    "internal_notes",
}
FINAL_NOTE_FORBIDDEN_PATTERNS = [
    r"source_profile",
    r"transcript_audit",
    r"segmentation_plan",
    r"target_attribution_ledger",
    r"evidence_ledger",
    r"suspect_confirmation",
    r"draft_review_report",
    r"qa_report",
    r"review_url",
    r"draft_id",
    r"history_url",
    r"Tool Call",
    r"Traceback",
    r"AI结构化总结",
    r"标的汇总表",
]


def load_json(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except UnicodeDecodeError as exc:
        raise ValueError(f"不是有效 UTF-8: {path}: {exc}") from exc
    except json.JSONDecodeError as exc:
        raise ValueError(f"不是有效 JSON: {path}: {exc}") from exc


def nested_keys(value: Any) -> set[str]:
    keys: set[str] = set()
    if isinstance(value, dict):
        for key, child in value.items():
            keys.add(str(key))
            keys.update(nested_keys(child))
    elif isinstance(value, list):
        for item in value:
            keys.update(nested_keys(item))
    return keys


def validate_common(payload: dict[str, Any], label: str) -> list[str]:
    errors: list[str] = []
    for field in COMMON_FIELDS:
        if field not in payload:
            errors.append(f"{label}: 缺少公共字段 {field}")
    artifact_type = payload.get("artifact_type")
    if artifact_type not in VALID_ARTIFACT_TYPES:
        errors.append(f"{label}: artifact_type 不合法: {artifact_type}")
    if payload.get("artifact_version") != ARTIFACT_VERSION:
        errors.append(f"{label}: artifact_version 必须为 {ARTIFACT_VERSION}")
    source_hash = str(payload.get("source_hash", ""))
    if not (source_hash.startswith("sha256:") or source_hash.startswith("unavailable:")):
        errors.append(f"{label}: source_hash 必须以 sha256: 或 unavailable: 开头")
    if payload.get("status") not in VALID_STATUSES:
        errors.append(f"{label}: status 不合法: {payload.get('status')}")
    if "input_refs" in payload and not isinstance(payload["input_refs"], list):
        errors.append(f"{label}: input_refs 必须是数组")
    if "warnings" in payload and not isinstance(payload["warnings"], list):
        errors.append(f"{label}: warnings 必须是数组")
    if "requires_human_review" in payload and not isinstance(payload["requires_human_review"], bool):
        errors.append(f"{label}: requires_human_review 必须是布尔值")
    return errors


def validate_source_profile(payload: dict[str, Any], label: str) -> list[str]:
    required = [
        "input_mode",
        "files",
        "meeting_type_candidate",
        "has_audio",
        "has_document",
        "has_timestamp",
        "known_speakers",
        "known_targets",
        "sensitive_terms",
        "processing_notes",
    ]
    errors = [f"{label}: source_profile 缺少 {field}" for field in required if field not in payload]
    if payload.get("input_mode") not in {"audio_only", "document_only", "audio_plus_document"}:
        errors.append(f"{label}: input_mode 不合法: {payload.get('input_mode')}")
    return errors


def validate_transcript_audit(payload: dict[str, Any], label: str) -> list[str]:
    required = [
        "input_mode",
        "speaker_boundary_issues",
        "timestamp_anchors",
        "low_confidence_terms",
        "asr_conflicts",
        "audio_document_conflicts",
        "suspected_entities",
    ]
    return [f"{label}: transcript_audit 缺少 {field}" for field in required if field not in payload]


def validate_segmentation_plan(payload: dict[str, Any], label: str) -> list[str]:
    required = ["meeting_type", "speech_order", "segments", "split_required", "merge_forbidden"]
    errors = [f"{label}: segmentation_plan 缺少 {field}" for field in required if field not in payload]
    for index, segment in enumerate(payload.get("segments", []), start=1):
        for field in ["segment_id", "speaker", "source_refs", "topic_hint", "target_hint", "reason_for_split"]:
            if field not in segment:
                errors.append(f"{label}: segments[{index}] 缺少 {field}")
    return errors


def validate_target_attribution(payload: dict[str, Any], label: str) -> list[str]:
    errors: list[str] = []
    segments = payload.get("segments")
    if not isinstance(segments, list) or not segments:
        return [f"{label}: target_attribution_ledger 必须包含非空 segments"]
    for index, segment in enumerate(segments, start=1):
        for field in [
            "segment_id",
            "primary_target",
            "mentioned_targets",
            "recommendation_target",
            "target_roles",
            "title_requirement",
            "attribution_confidence",
            "attribution_notes",
        ]:
            if field not in segment:
                errors.append(f"{label}: segments[{index}] 缺少 {field}")
        if "mentioned_targets" in segment and not isinstance(segment["mentioned_targets"], list):
            errors.append(f"{label}: segments[{index}].mentioned_targets 必须是数组")
        if "target_roles" in segment and not isinstance(segment["target_roles"], dict):
            errors.append(f"{label}: segments[{index}].target_roles 必须是对象")
    return errors


def validate_evidence(payload: dict[str, Any], label: str) -> list[str]:
    errors: list[str] = []
    claims = payload.get("claims")
    if not isinstance(claims, list) or not claims:
        return [f"{label}: evidence_ledger 必须包含非空 claims"]
    for index, claim in enumerate(claims, start=1):
        for field in [
            "claim_id",
            "claim_type",
            "claim_text",
            "source_refs",
            "source_evidence",
            "local_reference_evidence",
            "external_verification_path",
            "evidence_status",
            "final_handling",
        ]:
            if field not in claim:
                errors.append(f"{label}: claims[{index}] 缺少 {field}")
        if claim.get("evidence_status") not in VALID_EVIDENCE_STATUS:
            errors.append(f"{label}: claims[{index}].evidence_status 不合法: {claim.get('evidence_status')}")
    return errors


def validate_suspect(payload: dict[str, Any], label: str) -> list[str]:
    errors: list[str] = []
    items = payload.get("items")
    if not isinstance(items, list):
        return [f"{label}: suspect_confirmation.items 必须是数组"]
    for index, item in enumerate(items, start=1):
        for field in [
            "item_id",
            "source_refs",
            "original_expression",
            "current_judgment",
            "uncertainty_reason",
            "candidate_values",
            "context",
            "suggested_confirmation_path",
            "final_note_handling",
        ]:
            if field not in item:
                errors.append(f"{label}: items[{index}] 缺少 {field}")
        context = str(item.get("context", "")).strip()
        path = str(item.get("suggested_confirmation_path", "")).strip()
        reason = str(item.get("uncertainty_reason", "")).strip()
        if not context or not path or not reason:
            errors.append(f"{label}: items[{index}] 必须包含上下文、存疑原因和建议确认路径")
    return errors


def validate_review_report(payload: dict[str, Any], label: str) -> list[str]:
    return [f"{label}: draft_review_report 缺少 {field}" for field in ["findings", "checked_dimensions", "go_status"] if field not in payload]


def validate_qa_report(payload: dict[str, Any], label: str) -> list[str]:
    errors = [f"{label}: qa_report 缺少 {field}" for field in ["checks", "go_status", "no_go_reasons"] if field not in payload]
    for index, check in enumerate(payload.get("checks", []), start=1):
        for field in ["check_name", "command", "ok", "errors", "warnings"]:
            if field not in check:
                errors.append(f"{label}: checks[{index}] 缺少 {field}")
    return errors


def validate_rag_sidecar(payload: dict[str, Any], label: str) -> list[str]:
    forbidden = sorted(nested_keys(payload) & RAG_FORBIDDEN_KEYS)
    if forbidden:
        return [f"{label}: rag_sidecar 包含禁止字段: {', '.join(forbidden)}"]
    return []


def validate_artifact(path: Path) -> dict[str, Any]:
    errors: list[str] = []
    warnings: list[str] = []
    try:
        payload = load_json(path)
    except ValueError as exc:
        return {"path": str(path), "ok": False, "errors": [str(exc)], "warnings": []}
    if not isinstance(payload, dict):
        return {"path": str(path), "ok": False, "errors": ["artifact 顶层必须是对象"], "warnings": []}

    label = str(path)
    errors.extend(validate_common(payload, label))
    artifact_type = payload.get("artifact_type")
    if artifact_type == "source_profile":
        errors.extend(validate_source_profile(payload, label))
    elif artifact_type == "transcript_audit":
        errors.extend(validate_transcript_audit(payload, label))
    elif artifact_type == "segmentation_plan":
        errors.extend(validate_segmentation_plan(payload, label))
    elif artifact_type == "target_attribution_ledger":
        errors.extend(validate_target_attribution(payload, label))
    elif artifact_type == "evidence_ledger":
        errors.extend(validate_evidence(payload, label))
    elif artifact_type == "suspect_confirmation":
        errors.extend(validate_suspect(payload, label))
    elif artifact_type == "draft_review_report":
        errors.extend(validate_review_report(payload, label))
    elif artifact_type == "qa_report":
        errors.extend(validate_qa_report(payload, label))
    elif artifact_type == "rag_sidecar":
        errors.extend(validate_rag_sidecar(payload, label))
    return {"path": str(path), "ok": not errors, "errors": errors, "warnings": warnings}


def validate_final_markdown(path: Path, required_terms: list[str] | None = None) -> dict[str, Any]:
    errors: list[str] = []
    warnings: list[str] = []
    try:
        markdown = path.read_text(encoding="utf-8")
    except UnicodeDecodeError as exc:
        return {"path": str(path), "ok": False, "errors": [f"不是有效 UTF-8: {exc}"], "warnings": []}
    if not re.search(r"(?m)^# 投资会议纪要", markdown):
        errors.append("终稿必须以 # 投资会议纪要 开头")
    if "## 一、逐发言人原文整理" not in markdown:
        errors.append("终稿缺少 ## 一、逐发言人原文整理")
    for pattern in FINAL_NOTE_FORBIDDEN_PATTERNS:
        if re.search(pattern, markdown, re.IGNORECASE):
            errors.append(f"终稿包含禁止过程字段或旧格式: {pattern}")
    for term in required_terms or []:
        if term not in markdown:
            errors.append(f"终稿缺少 MAS 样例关键锚点: {term}")
    return {"path": str(path), "ok": not errors, "errors": errors, "warnings": warnings}


def validate_cases(cases_path: Path) -> dict[str, Any]:
    payload = load_json(cases_path)
    cases = payload.get("cases") if isinstance(payload, dict) else None
    if not isinstance(cases, list):
        raise ValueError(f"cases 文件必须包含 cases 数组: {cases_path}")
    base_dir = cases_path.parent
    results: list[dict[str, Any]] = []
    for case in cases:
        case_name = str(case.get("name") or "unnamed")
        artifact_results = [
            validate_artifact(base_dir / str(path))
            for path in case.get("artifacts", [])
        ]
        final_markdown = case.get("final_markdown")
        final_result = None
        if final_markdown:
            final_result = validate_final_markdown(
                base_dir / str(final_markdown),
                [str(term) for term in case.get("required_terms", [])],
            )
        case_errors: list[str] = []
        for item in artifact_results:
            case_errors.extend(item["errors"])
        if final_result:
            case_errors.extend(final_result["errors"])
        results.append(
            {
                "name": case_name,
                "mode": case.get("mode", ""),
                "ok": not case_errors,
                "errors": case_errors,
                "artifacts": artifact_results,
                "final_markdown": final_result,
            }
        )
    return {"ok": all(result["ok"] for result in results), "case_count": len(results), "results": results}


def main() -> int:
    parser = argparse.ArgumentParser(description="校验 Skill-first MAS sidecar artifacts")
    parser.add_argument("artifacts", nargs="*", help="单个 artifact JSON 文件")
    parser.add_argument("--cases", help="MAS regression cases JSON")
    parser.add_argument("--final-markdown", help="额外校验终稿 Markdown 不含过程字段")
    parser.add_argument("--require-term", action="append", default=[], help="终稿必须包含的关键锚点")
    parser.add_argument("--json", action="store_true", help="输出 JSON")
    args = parser.parse_args()

    try:
        if args.cases:
            result = validate_cases(Path(args.cases).expanduser())
        else:
            artifact_results = [validate_artifact(Path(path).expanduser()) for path in args.artifacts]
            final_result = (
                validate_final_markdown(Path(args.final_markdown).expanduser(), args.require_term)
                if args.final_markdown
                else None
            )
            ok = all(item["ok"] for item in artifact_results) and (final_result is None or final_result["ok"])
            result = {"ok": ok, "artifacts": artifact_results, "final_markdown": final_result}
    except ValueError as exc:
        result = {"ok": False, "errors": [str(exc)], "warnings": []}

    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        if result["ok"]:
            print("MAS artifacts: ok")
        else:
            print(json.dumps(result, ensure_ascii=False, indent=2), file=sys.stderr)
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
