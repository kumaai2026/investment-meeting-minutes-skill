#!/usr/bin/env python3
"""Validate conditional Subagent analysis ledgers and QA reports."""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any

ARTIFACT_TYPE = "investment_meeting_analysis_ledger"
ARTIFACT_VERSION = "subagent.v1"
TARGET_ROLES = {
    "primary_target",
    "recommendation_target",
    "comparison_target",
    "customer",
    "supplier",
    "competitor",
    "upstream",
    "downstream",
    "industry_background",
    "incidental",
    "unclear",
}
ACTIONS = {
    "recommend",
    "positive",
    "hold",
    "watch",
    "trade_opportunity",
    "reduce",
    "avoid",
    "negative",
    "neutral",
    "unclear",
}
STANCES = {"positive", "neutral", "negative", "mixed", "unclear"}
TICKER_STATUS = {"confirmed", "candidate_only", "unverified", "not_found", "not_applicable"}
LEDGER_STATUSES = {"draft", "reviewed", "needs_review", "blocked"}
PRIVACY_PATTERNS = [
    re.compile(r"/Users/"),
    re.compile(r"[A-Za-z]:\\"),
    re.compile(r"file://", re.I),
    re.compile(r"https?://[^ \t\n\"']*(?:review|draft|history)[^ \t\n\"']*", re.I),
    re.compile(r"token=", re.I),
    re.compile(r"api_key", re.I),
    re.compile(r"Authorization", re.I),
    re.compile(r"Bearer\s+\S+", re.I),
    re.compile(r"cookie", re.I),
    re.compile(r"https?://(?:localhost|127\.0\.0\.1):(?:8767|1000|18081)[^ \t\n\"']*", re.I),
]
HARD_QA_STATUSES = {"go", "pass"}
HIGH_SEVERITY = {"high", "critical", "blocker"}


def load_json(path: Path) -> tuple[Any | None, list[str], bool]:
    try:
        return json.loads(path.read_text(encoding="utf-8")), [], False
    except (FileNotFoundError, PermissionError, OSError, json.JSONDecodeError, UnicodeDecodeError) as exc:
        return None, [f"{path}: {type(exc).__name__}: {exc}"], True


def find_privacy_leaks(value: Any, path: str = "$") -> list[str]:
    leaks: list[str] = []
    if isinstance(value, dict):
        for key, child in value.items():
            key_text = str(key)
            for pattern in PRIVACY_PATTERNS:
                if pattern.search(key_text):
                    leaks.append(f"{path}.{key_text}: privacy key/value pattern matched {pattern.pattern}")
            leaks.extend(find_privacy_leaks(child, f"{path}.{key_text}"))
    elif isinstance(value, list):
        for index, item in enumerate(value):
            leaks.extend(find_privacy_leaks(item, f"{path}[{index}]"))
    elif isinstance(value, str):
        for pattern in PRIVACY_PATTERNS:
            if pattern.search(value):
                leaks.append(f"{path}: privacy string pattern matched {pattern.pattern}")
    return leaks


def require_object(value: Any, label: str, errors: list[str]) -> dict[str, Any]:
    if not isinstance(value, dict):
        errors.append(f"{label}: must be an object")
        return {}
    return value


def require_list(value: Any, label: str, errors: list[str]) -> list[Any]:
    if not isinstance(value, list):
        errors.append(f"{label}: must be a list")
        return []
    return value


def validate_high_risk_claim(claim: dict[str, Any], label: str, errors: list[str]) -> None:
    required = [
        "claim_id",
        "claim_type",
        "claim_text",
        "source_ref",
        "source_evidence",
        "external_verification_path",
        "evidence_status",
        "final_handling",
    ]
    for field in required:
        if field not in claim:
            errors.append(f"{label}: missing {field}")
    if claim.get("evidence_status") not in {"confirmed", "candidate_only", "conflicting", "unverified", "not_found", "not_applicable"}:
        errors.append(f"{label}: invalid evidence_status {claim.get('evidence_status')}")


def validate_segment(segment: dict[str, Any], segment_ids: set[str], errors: list[str]) -> None:
    label = f"segment {segment.get('segment_id') or '<missing>'}"
    required = [
        "segment_id",
        "speaker_ref",
        "source_ref",
        "source_span",
        "topic",
        "pure_topic",
        "targets",
        "primary_target_ids",
        "recommendation_target_ids",
        "heading_target_ids",
        "suggested_heading",
        "final_heading",
        "split_required",
        "heading_exception_reason",
        "high_risk_claims",
        "unresolved_items",
    ]
    for field in required:
        if field not in segment:
            errors.append(f"{label}: missing {field}")

    segment_id = str(segment.get("segment_id") or "")
    if not segment_id:
        errors.append(f"{label}: segment_id is required")
    elif segment_id in segment_ids:
        errors.append(f"{label}: duplicate segment_id")
    segment_ids.add(segment_id)

    targets = require_list(segment.get("targets", []), f"{label}.targets", errors)
    target_ids: set[str] = set()
    for index, raw_target in enumerate(targets):
        target = require_object(raw_target, f"{label}.targets[{index}]", errors)
        target_id = str(target.get("target_id") or "")
        if not target_id:
            errors.append(f"{label}.targets[{index}]: target_id is required")
        elif target_id in target_ids:
            errors.append(f"{label}: duplicate target_id {target_id}")
        target_ids.add(target_id)

        roles = require_list(target.get("roles", []), f"{label}.{target_id}.roles", errors)
        invalid_roles = sorted(str(role) for role in roles if role not in TARGET_ROLES)
        if invalid_roles:
            errors.append(f"{label}.{target_id}: invalid roles {', '.join(invalid_roles)}")
        if target.get("action") not in ACTIONS:
            errors.append(f"{label}.{target_id}: invalid action {target.get('action')}")
        if target.get("stance") not in STANCES:
            errors.append(f"{label}.{target_id}: invalid stance {target.get('stance')}")
        if target.get("ticker_status") not in TICKER_STATUS:
            errors.append(f"{label}.{target_id}: invalid ticker_status {target.get('ticker_status')}")
        if target.get("ticker_status") != "confirmed" and target.get("ticker"):
            target["__unconfirmed_ticker_seen"] = True

    for field in ("primary_target_ids", "recommendation_target_ids", "heading_target_ids"):
        ids = require_list(segment.get(field, []), f"{label}.{field}", errors)
        missing = sorted(str(item) for item in ids if str(item) not in target_ids)
        if missing:
            errors.append(f"{label}.{field}: references missing target ids {', '.join(missing)}")

    by_id = {str(target.get("target_id")): target for target in targets if isinstance(target, dict)}
    for target_id in segment.get("recommendation_target_ids", []):
        target = by_id.get(str(target_id), {})
        roles = target.get("roles") if isinstance(target.get("roles"), list) else []
        if "recommendation_target" not in roles:
            errors.append(f"{label}.{target_id}: recommendation target missing recommendation_target role")
        if target.get("explicit_recommendation") is not True:
            errors.append(f"{label}.{target_id}: recommendation target must set explicit_recommendation=true")
        if not str(target.get("evidence_span") or "").strip():
            errors.append(f"{label}.{target_id}: recommendation target missing evidence_span")
        if not str(target.get("confidence") or "").strip():
            errors.append(f"{label}.{target_id}: recommendation target missing confidence")

    for index, raw_claim in enumerate(require_list(segment.get("high_risk_claims", []), f"{label}.high_risk_claims", errors)):
        validate_high_risk_claim(require_object(raw_claim, f"{label}.high_risk_claims[{index}]", errors), f"{label}.high_risk_claims[{index}]", errors)


def validate_qa_report(payload: dict[str, Any], errors: list[str]) -> None:
    for field in ("checks", "go_status", "no_go_reasons", "requires_human_review", "subagent_status"):
        if field not in payload:
            errors.append(f"qa_report: missing {field}")
    checks = require_list(payload.get("checks", []), "qa_report.checks", errors)
    failed = []
    for index, raw_check in enumerate(checks):
        check = require_object(raw_check, f"qa_report.checks[{index}]", errors)
        for field in ("check_name", "command", "ok", "errors", "warnings"):
            if field not in check:
                errors.append(f"qa_report.checks[{index}]: missing {field}")
        if check.get("ok") is not True:
            failed.append(str(check.get("check_name") or index))
    if failed and str(payload.get("go_status") or "").lower() in HARD_QA_STATUSES:
        errors.append(f"qa_report: failed checks cannot have GO status: {', '.join(failed)}")
    if failed and not payload.get("no_go_reasons"):
        errors.append("qa_report: failed checks require no_go_reasons")


def validate_ledger(payload: dict[str, Any], qa_payload: dict[str, Any] | None = None) -> dict[str, Any]:
    errors: list[str] = []
    warnings: list[str] = []

    if payload.get("artifact_type") != ARTIFACT_TYPE:
        errors.append(f"artifact_type must be {ARTIFACT_TYPE}")
    if payload.get("artifact_version") != ARTIFACT_VERSION:
        errors.append(f"artifact_version must be {ARTIFACT_VERSION}")
    if payload.get("status") not in LEDGER_STATUSES:
        errors.append(f"invalid status {payload.get('status')}")
    if not isinstance(payload.get("requires_human_review"), bool):
        errors.append("requires_human_review must be boolean")

    require_object(payload.get("source_profile", {}), "source_profile", errors)
    transcript_audit = require_object(payload.get("transcript_audit", {}), "transcript_audit", errors)
    if "status" not in transcript_audit or "findings" not in transcript_audit:
        errors.append("transcript_audit requires status and findings")

    segment_ids: set[str] = set()
    segments = require_list(payload.get("segments", []), "segments", errors)
    for raw_segment in segments:
        validate_segment(require_object(raw_segment, "segment", errors), segment_ids, errors)

    has_unresolved = any(bool(segment.get("unresolved_items")) for segment in segments if isinstance(segment, dict))
    if has_unresolved and payload.get("requires_human_review") is not True:
        errors.append("unresolved_items requires top-level requires_human_review=true")

    post_draft = require_object(payload.get("post_draft_review", {}), "post_draft_review", errors)
    findings = post_draft.get("findings", [])
    if isinstance(findings, list):
        unresolved_high = [
            finding
            for finding in findings
            if isinstance(finding, dict)
            and str(finding.get("severity") or "").lower() in HIGH_SEVERITY
            and str(finding.get("status") or "open").lower() not in {"resolved", "accepted"}
        ]
        if unresolved_high and str(post_draft.get("go_status") or "").lower() in HARD_QA_STATUSES:
            errors.append("post_draft_review has unresolved high severity findings but GO status")
    else:
        errors.append("post_draft_review.findings must be a list")

    if qa_payload is not None:
        validate_qa_report(qa_payload, errors)

    privacy_leaks = find_privacy_leaks(payload)
    if qa_payload is not None:
        privacy_leaks.extend(find_privacy_leaks(qa_payload, "$qa_report"))
    errors.extend(privacy_leaks)

    return {"ok": not errors, "errors": errors, "warnings": warnings}


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate conditional Subagent analysis ledger")
    parser.add_argument("ledger", nargs="?", help="analysis_ledger.json")
    parser.add_argument("--qa-report", help="optional qa_report.json")
    parser.add_argument("--json", action="store_true", help="output JSON")
    args = parser.parse_args()

    if not args.ledger:
        payload = {"ok": False, "errors": ["ledger argument is required"], "warnings": []}
        print(json.dumps(payload, ensure_ascii=False, indent=2) if args.json else "ledger argument is required")
        return 2

    ledger_payload, load_errors, operational = load_json(Path(args.ledger).expanduser())
    if operational:
        payload = {"ok": False, "errors": load_errors, "warnings": []}
        print(json.dumps(payload, ensure_ascii=False, indent=2) if args.json else "\n".join(load_errors))
        return 2
    if not isinstance(ledger_payload, dict):
        payload = {"ok": False, "errors": ["ledger top-level must be an object"], "warnings": []}
        print(json.dumps(payload, ensure_ascii=False, indent=2) if args.json else "ledger top-level must be an object")
        return 1

    qa_payload = None
    if args.qa_report:
        qa_payload, qa_errors, qa_operational = load_json(Path(args.qa_report).expanduser())
        if qa_operational:
            payload = {"ok": False, "errors": qa_errors, "warnings": []}
            print(json.dumps(payload, ensure_ascii=False, indent=2) if args.json else "\n".join(qa_errors))
            return 2
        if not isinstance(qa_payload, dict):
            payload = {"ok": False, "errors": ["qa_report top-level must be an object"], "warnings": []}
            print(json.dumps(payload, ensure_ascii=False, indent=2) if args.json else "qa_report top-level must be an object")
            return 1

    result = validate_ledger(ledger_payload, qa_payload)
    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        print("ok" if result["ok"] else "fail")
        for warning in result["warnings"]:
            print(f"warning: {warning}", file=sys.stderr)
        for error in result["errors"]:
            print(f"error: {error}", file=sys.stderr)
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
