#!/usr/bin/env python3
"""Prepare or apply non-destructive repairs for Dify dataset mapping drift."""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

SCRIPT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPT_DIR))

from audit_dify_dataset_mapping import DEFAULT_MAPPING_PATH, mapping_source_path, read_json  # noqa: E402
from sync_minutes_to_dify_dataset import (  # noqa: E402
    build_metadata,
    load_config,
    mapping_path_from_config,
    sync_markdown_to_dify,
)


def document_id_groups(mapping: dict[str, Any]) -> dict[str, list[str]]:
    groups: dict[str, list[str]] = defaultdict(list)
    for key, value in mapping.items():
        if isinstance(value, dict) and value.get("document_id"):
            groups[str(value["document_id"])].append(key)
    return groups


def planned_item(key: str, value: dict[str, Any], *, status: str, message: str, **extra: Any) -> dict[str, Any]:
    item: dict[str, Any] = {
        "key": key,
        "status": status,
        "message": message,
        "document_id": str(value.get("document_id") or ""),
        "current_document_name": str(value.get("document_name") or ""),
    }
    item.update(extra)
    return item


def build_plan(mapping: dict[str, Any], *, include_ok: bool = False) -> list[dict[str, Any]]:
    groups = document_id_groups(mapping)
    plan: list[dict[str, Any]] = []
    for key, raw_value in sorted(mapping.items()):
        if not isinstance(raw_value, dict):
            plan.append(
                {
                    "key": key,
                    "status": "skipped_invalid_mapping_value",
                    "message": "mapping value 不是对象",
                    "document_id": "",
                    "current_document_name": "",
                }
            )
            continue

        source_path = mapping_source_path(key)
        if source_path is None:
            plan.append(planned_item(key, raw_value, status="skipped_not_path_key", message="非本地文件路径 key"))
            continue
        if not source_path.exists():
            plan.append(
                planned_item(
                    key,
                    raw_value,
                    status="skipped_missing_source",
                    message="源 Markdown 不存在，跳过",
                    source_path=str(source_path),
                )
            )
            continue

        document_id = str(raw_value.get("document_id") or "")
        if not document_id:
            plan.append(
                planned_item(
                    key,
                    raw_value,
                    status="skipped_no_document_id",
                    message="mapping 中没有 document_id，禁止按同名搜索自动选择",
                    source_path=str(source_path),
                )
            )
            continue

        shared_keys = groups.get(document_id, [])
        if len(shared_keys) > 1:
            plan.append(
                planned_item(
                    key,
                    raw_value,
                    status="skipped_shared_document_id",
                    message="同一 document_id 被多个 key 引用，避免误更新",
                    source_path=str(source_path),
                    shared_keys=shared_keys,
                )
            )
            continue

        markdown = source_path.read_text(encoding="utf-8")
        metadata = build_metadata(markdown, source_file=source_path, markdown_path=str(source_path), note_key=key)
        current_name = str(raw_value.get("document_name") or "")
        if current_name == metadata.document_name:
            if include_ok:
                plan.append(
                    planned_item(
                        key,
                        raw_value,
                        status="already_ok",
                        message="文档名已符合当前规则",
                        source_path=str(source_path),
                        expected_document_name=metadata.document_name,
                    )
                )
            continue

        plan.append(
            planned_item(
                key,
                raw_value,
                status="planned_update",
                message="可用 document_id 精确 update-by-text 修复名称和内容",
                source_path=str(source_path),
                expected_document_name=metadata.document_name,
                meeting_date=metadata.meeting_date,
            )
        )
    return plan


def summarize_plan(plan: list[dict[str, Any]]) -> dict[str, int]:
    counts = Counter(item["status"] for item in plan)
    return dict(sorted(counts.items()))


def apply_plan(plan: list[dict[str, Any]], *, config_path: Path, mapping_path: Path, limit: int | None = None) -> list[dict[str, Any]]:
    config = load_config(config_path)
    results: list[dict[str, Any]] = []
    applied = 0
    for item in plan:
        if item.get("status") != "planned_update":
            continue
        if limit is not None and applied >= limit:
            break
        source_path = Path(str(item["source_path"]))
        markdown = source_path.read_text(encoding="utf-8")
        metadata = build_metadata(
            markdown,
            source_file=source_path,
            markdown_path=str(source_path),
            note_key=str(item["key"]),
        )
        try:
            result = sync_markdown_to_dify(markdown, metadata, config=config, mapping_path=mapping_path)
        except Exception as exc:  # noqa: BLE001
            results.append({**item, "apply_status": "failed", "error": str(exc)})
            continue
        results.append(
            {
                **item,
                "apply_status": "updated" if result.ok else "failed",
                "action": result.action,
                "updated_document_id": result.document_id,
                "updated_document_name": result.document_name,
                "message": result.message,
            }
        )
        applied += 1
    return results


def print_text(plan: list[dict[str, Any]], applied: list[dict[str, Any]] | None = None) -> None:
    print("修复计划汇总:")
    for status, count in summarize_plan(plan).items():
        print(f"- {status}: {count}")
    print()
    for item in plan:
        if item["status"] == "planned_update":
            print(f"[PLAN] {item['document_id']}")
            print(f"  当前: {item['current_document_name']}")
            print(f"  期望: {item['expected_document_name']}")
            print(f"  源文件: {item['source_path']}")
        elif item["status"].startswith("skipped"):
            print(f"[SKIP] {item['status']} {item.get('document_id') or ''} {item['message']}")
            if item.get("source_path"):
                print(f"  源文件: {item['source_path']}")
    if applied is not None:
        print()
        print("执行结果:")
        if not applied:
            print("- 没有执行任何 update")
        for item in applied:
            print(f"- {item.get('apply_status')}: {item.get('updated_document_id') or item.get('document_id')}")
            print(f"  {item.get('message') or item.get('error')}")


def main() -> int:
    parser = argparse.ArgumentParser(description="非删除式修复 Dify 会议纪要知识库旧 backfill 映射")
    parser.add_argument("--mapping", default=str(mapping_path_from_config()), help="Dify 文档映射 JSON")
    parser.add_argument("--config", default=str(Path.home() / "Library/Application Support/kumaai-sync/dify-meeting-minutes.env"))
    parser.add_argument("--apply", action="store_true", help="执行 update-by-text；默认只 dry-run")
    parser.add_argument("--limit", type=int, help="最多执行多少条 planned_update")
    parser.add_argument("--include-ok", action="store_true", help="输出已符合规则的条目")
    parser.add_argument("--json", action="store_true", help="输出 JSON")
    args = parser.parse_args()

    mapping_path = Path(args.mapping).expanduser()
    config_path = Path(args.config).expanduser()
    mapping = read_json(mapping_path)
    plan = build_plan(mapping, include_ok=args.include_ok)
    applied = apply_plan(plan, config_path=config_path, mapping_path=mapping_path, limit=args.limit) if args.apply else None
    payload = {
        "ok": not any(item["status"] == "planned_update" for item in plan) if not args.apply else not any(item.get("apply_status") == "failed" for item in applied or []),
        "dry_run": not args.apply,
        "summary": summarize_plan(plan),
        "plan": plan,
        "applied": applied or [],
    }
    if args.json:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
    else:
        print_text(plan, applied)
    return 1 if any(item.get("apply_status") == "failed" for item in applied or []) else 0


if __name__ == "__main__":
    raise SystemExit(main())
