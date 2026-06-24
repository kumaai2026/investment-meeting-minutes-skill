#!/usr/bin/env python3
"""Run fixed local regression checks for the meeting-minutes contract."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

SCRIPT_DIR = Path(__file__).resolve().parent
SKILL_DIR = SCRIPT_DIR.parent
DEFAULT_CASES_PATH = SKILL_DIR / "references/regression_samples/cases.json"

sys.path.insert(0, str(SCRIPT_DIR))
from validate_meeting_minutes_contract import validate_contract  # noqa: E402
from validate_analysis_ledger import validate_ledger, load_json  # noqa: E402
from validate_title_target_consistency import validate as validate_title_target  # noqa: E402


def read_cases(path: Path) -> list[dict[str, Any]]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    cases = payload.get("cases")
    if not isinstance(cases, list):
        raise ValueError(f"回归样例格式错误: {path}")
    return cases


def run_case(case: dict[str, Any], base_dir: Path) -> dict[str, Any]:
    file_path = base_dir / str(case["file"])
    markdown = file_path.read_text(encoding="utf-8")
    result = validate_contract(
        markdown,
        required_terms=[str(term) for term in case.get("required_terms", [])],
        source_mode=str(case.get("source_mode") or case.get("mode") or "auto"),
        require_audio_timestamps=bool(case.get("require_audio_timestamps")),
    )
    result = {
        "name": case.get("name") or file_path.stem,
        "mode": case.get("mode") or "",
        "file": str(file_path),
        **result,
    }
    ledger_ref = case.get("analysis_ledger")
    if ledger_ref:
        ledger_path = base_dir / str(ledger_ref)
        qa_payload = None
        qa_ref = case.get("qa_report")
        if qa_ref:
            qa_payload, qa_errors, qa_operational = load_json(base_dir / str(qa_ref))
            if qa_operational:
                result["ok"] = False
                result.setdefault("errors", []).extend(qa_errors)
                return result
        ledger_payload, ledger_errors, ledger_operational = load_json(ledger_path)
        if ledger_operational or not isinstance(ledger_payload, dict):
            result["ok"] = False
            result.setdefault("errors", []).extend(ledger_errors or [f"{ledger_path}: ledger top-level must be object"])
            return result
        ledger_result = validate_ledger(ledger_payload, qa_payload if isinstance(qa_payload, dict) else None)
        title_result = validate_title_target(file_path, ledger_path)
        result["analysis_ledger"] = {"file": str(ledger_path), **ledger_result}
        result["title_target_consistency"] = title_result
        result["ok"] = bool(result["ok"] and ledger_result["ok"] and title_result["ok"])
        result.setdefault("errors", []).extend(f"analysis_ledger: {error}" for error in ledger_result["errors"])
        result.setdefault("errors", []).extend(f"title_target: {error}" for error in title_result["errors"])
        result.setdefault("warnings", []).extend(f"analysis_ledger: {warning}" for warning in ledger_result["warnings"])
        result.setdefault("warnings", []).extend(f"title_target: {warning}" for warning in title_result["warnings"])
    return result


def print_text(results: list[dict[str, Any]]) -> None:
    for result in results:
        status = "OK" if result["ok"] else "FAIL"
        print(f"[{status}] {result['name']} ({result['mode']})")
        for warning in result["warnings"]:
            print(f"  warning: {warning}")
        for error in result["errors"]:
            print(f"  error: {error}")


def main() -> int:
    parser = argparse.ArgumentParser(description="运行会议纪要固定回归样例")
    parser.add_argument("--cases", default=str(DEFAULT_CASES_PATH), help="回归样例 cases.json")
    parser.add_argument("--json", action="store_true", help="输出 JSON")
    args = parser.parse_args()

    cases_path = Path(args.cases).expanduser()
    base_dir = cases_path.parent
    results = [run_case(case, base_dir) for case in read_cases(cases_path)]
    payload = {
        "ok": all(result["ok"] for result in results),
        "case_count": len(results),
        "results": results,
    }
    if args.json:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
    else:
        print_text(results)
    return 0 if payload["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
