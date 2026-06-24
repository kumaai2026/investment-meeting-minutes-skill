#!/usr/bin/env python3
"""Score target attribution output against human gold labels."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

PROBLEM_ROLES = {"customer", "supplier", "comparison_target"}


def load(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"{path}: top-level must be an object")
    return payload


def case_map(payload: dict[str, Any]) -> dict[str, dict[str, Any]]:
    cases = payload.get("cases")
    if not isinstance(cases, list):
        raise ValueError("payload must contain cases list")
    result = {}
    for case in cases:
        if not isinstance(case, dict) or not case.get("case_id"):
            raise ValueError("each case requires case_id")
        result[str(case["case_id"])] = case
    return result


def as_set(value: Any) -> set[str]:
    if not isinstance(value, list):
        return set()
    return {str(item) for item in value}


def prf(tp: int, fp: int, fn: int) -> dict[str, float | int]:
    precision = tp / (tp + fp) if tp + fp else 1.0
    recall = tp / (tp + fn) if tp + fn else 1.0
    return {"tp": tp, "fp": fp, "fn": fn, "precision": precision, "recall": recall}


def score(actual: dict[str, Any], gold: dict[str, Any]) -> dict[str, Any]:
    actual_cases = case_map(actual)
    gold_cases = case_map(gold)
    primary_tp = primary_fp = primary_fn = 0
    rec_tp = rec_fp = rec_fn = 0
    heading_ok = heading_total = 0
    action_ok = action_total = 0
    role_false_positives: list[dict[str, str]] = []
    problem_role_rec_fp = 0

    for case_id, gold_case in gold_cases.items():
        actual_case = actual_cases.get(case_id, {})
        actual_primary = as_set(actual_case.get("primary_target_ids"))
        gold_primary = as_set(gold_case.get("primary_target_ids"))
        primary_tp += len(actual_primary & gold_primary)
        primary_fp += len(actual_primary - gold_primary)
        primary_fn += len(gold_primary - actual_primary)

        actual_rec = as_set(actual_case.get("recommendation_target_ids"))
        gold_rec = as_set(gold_case.get("recommendation_target_ids"))
        rec_tp += len(actual_rec & gold_rec)
        rec_fp += len(actual_rec - gold_rec)
        rec_fn += len(gold_rec - actual_rec)

        heading_total += 1
        if gold_rec <= as_set(actual_case.get("heading_target_ids")):
            heading_ok += 1

        gold_actions = gold_case.get("actions") if isinstance(gold_case.get("actions"), dict) else {}
        actual_actions = actual_case.get("actions") if isinstance(actual_case.get("actions"), dict) else {}
        for target_id, expected_action in gold_actions.items():
            action_total += 1
            if actual_actions.get(target_id) == expected_action:
                action_ok += 1

        gold_roles = gold_case.get("roles") if isinstance(gold_case.get("roles"), dict) else {}
        actual_roles = actual_case.get("roles") if isinstance(actual_case.get("roles"), dict) else {}
        for target_id, roles in actual_roles.items():
            actual_role_set = set(roles if isinstance(roles, list) else [])
            gold_role_set = set(gold_roles.get(target_id, []))
            for extra in sorted(actual_role_set - gold_role_set):
                role_false_positives.append({"case_id": case_id, "target_id": target_id, "role": extra})
                if extra == "recommendation_target" and gold_role_set & PROBLEM_ROLES:
                    problem_role_rec_fp += 1

    return {
        "ok": not role_false_positives and rec_fn == 0 and primary_fn == 0,
        "case_count": len(gold_cases),
        "primary_target": prf(primary_tp, primary_fp, primary_fn),
        "recommendation_target": prf(rec_tp, rec_fp, rec_fn),
        "role_false_positives": role_false_positives,
        "customer_supplier_comparison_recommendation_false_positives": problem_role_rec_fp,
        "heading_coverage": heading_ok / heading_total if heading_total else 1.0,
        "action_classification_accuracy": action_ok / action_total if action_total else 1.0,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Score target attribution output")
    parser.add_argument("--actual", required=True)
    parser.add_argument("--gold", required=True)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    try:
        result = score(load(Path(args.actual).expanduser()), load(Path(args.gold).expanduser()))
    except (FileNotFoundError, PermissionError, OSError, UnicodeDecodeError, json.JSONDecodeError, ValueError) as exc:
        result = {"ok": False, "errors": [f"{type(exc).__name__}: {exc}"]}
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 2

    print(json.dumps(result, ensure_ascii=False, indent=2) if args.json else result)
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
