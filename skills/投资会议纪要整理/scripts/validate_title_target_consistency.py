#!/usr/bin/env python3
"""Validate final Markdown headings against an analysis ledger."""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any

SCRIPT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPT_DIR))
from validate_meeting_minutes_contract import validate_contract  # noqa: E402

PROCESS_FIELDS = [
    "analysis_ledger",
    "qa_report",
    "artifact_type",
    "artifact_version",
    "source_profile",
    "transcript_audit",
    "post_draft_review",
    "recommendation_target_ids",
    "heading_target_ids",
]
ROLE_BLOCKED_WHEN_RECOMMENDATION = {"customer", "supplier", "comparison_target"}


def load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def target_name_in_text(name: str, text: str) -> bool:
    return bool(name) and name in text


def validate(markdown_path: Path, ledger_path: Path) -> dict[str, Any]:
    errors: list[str] = []
    warnings: list[str] = []
    try:
        markdown = markdown_path.read_text(encoding="utf-8")
        ledger = load_json(ledger_path)
    except (FileNotFoundError, PermissionError, OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        return {"ok": False, "errors": [f"{type(exc).__name__}: {exc}"], "warnings": []}

    contract = validate_contract(markdown)
    errors.extend(f"markdown_contract: {error}" for error in contract.get("errors", []))
    warnings.extend(f"markdown_contract: {warning}" for warning in contract.get("warnings", []))

    for field in PROCESS_FIELDS:
        if re.search(rf"\b{re.escape(field)}\b", markdown):
            errors.append(f"final Markdown leaks internal field: {field}")

    if not isinstance(ledger, dict):
        errors.append("ledger top-level must be an object")
        return {"ok": False, "errors": errors, "warnings": warnings}

    for segment in ledger.get("segments", []):
        if not isinstance(segment, dict):
            errors.append("ledger segment must be an object")
            continue
        segment_id = str(segment.get("segment_id") or "<missing>")
        final_heading = str(segment.get("final_heading") or "").strip()
        if final_heading and final_heading not in markdown:
            errors.append(f"{segment_id}: final_heading not found in Markdown: {final_heading}")

        targets = {
            str(target.get("target_id")): target
            for target in segment.get("targets", [])
            if isinstance(target, dict)
        }
        heading_ids = {str(item) for item in segment.get("heading_target_ids", [])}
        recommendation_ids = {str(item) for item in segment.get("recommendation_target_ids", [])}

        for target_id in heading_ids:
            if target_id not in targets:
                errors.append(f"{segment_id}: heading target {target_id} not in current segment")

        exception = str(segment.get("heading_exception_reason") or "").strip()
        missing_recommendations = sorted(recommendation_ids - heading_ids)
        if missing_recommendations and not exception:
            errors.append(f"{segment_id}: recommendation target missing from heading_target_ids: {', '.join(missing_recommendations)}")

        for target_id in recommendation_ids:
            target = targets.get(target_id, {})
            display_name = str(target.get("display_name") or "").strip()
            if final_heading and display_name and display_name not in final_heading and not exception:
                errors.append(f"{segment_id}: recommendation target {display_name} not in final_heading")

        if recommendation_ids and heading_ids:
            heading_roles = set()
            for target_id in heading_ids:
                roles = targets.get(target_id, {}).get("roles")
                if isinstance(roles, list):
                    heading_roles.update(str(role) for role in roles)
            if heading_roles and heading_roles <= ROLE_BLOCKED_WHEN_RECOMMENDATION:
                errors.append(f"{segment_id}: customer/supplier/comparison is the only heading role while recommendation exists")

        for target_id in heading_ids:
            target = targets.get(target_id, {})
            ticker = str(target.get("ticker") or "").strip()
            if ticker and target.get("ticker_status") != "confirmed" and final_heading and ticker in final_heading:
                errors.append(f"{segment_id}: unconfirmed ticker appears in final heading: {ticker}")

    return {"ok": not errors, "errors": errors, "warnings": warnings}


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate Markdown title-target consistency")
    parser.add_argument("note_md")
    parser.add_argument("analysis_ledger")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    result = validate(Path(args.note_md).expanduser(), Path(args.analysis_ledger).expanduser())
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
