#!/usr/bin/env python3
"""Audit local Obsidian minutes against the Dify dataset mapping file."""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Any

DEFAULT_MINUTES_DIR = Path("/Users/kumaai/Documents/Codex/workspace/投资纪要工作流/01 Projects/会议纪要")
DEFAULT_MAPPING_PATH = Path(
    "/Users/kumaai/Library/Application Support/kumaai-sync/meeting-minutes-review/dify_dataset_documents.json"
)


def read_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def markdown_field(markdown: str, field: str) -> str:
    pattern = re.compile(rf"^\*\*{re.escape(field)}\*\*[:：]\s*(.+?)\s*$", re.MULTILINE)
    match = pattern.search(markdown)
    return match.group(1).strip() if match else ""


def markdown_title(markdown: str, fallback: str) -> str:
    for line in markdown.splitlines():
        stripped = line.strip()
        if stripped.startswith("# "):
            return stripped[2:].strip() or fallback
    return fallback


def date_from_path(path: Path) -> str:
    match = re.search(r"20\d{2}-\d{2}-\d{2}", str(path))
    return match.group(0) if match else ""


def expected_document_name(path: Path, markdown: str) -> str:
    meeting_date = markdown_field(markdown, "会议日期") or date_from_path(path)
    title = markdown_title(markdown, path.stem)
    if title in {"投资会议纪要", "会议纪要"}:
        title = re.sub(r"^20\d{2}-\d{2}-\d{2}\s*-\s*", "", path.stem).strip() or title
        if title in {"投资会议纪要", "会议纪要"}:
            path_date = date_from_path(path)
            if meeting_date and path_date and path_date != meeting_date:
                title = f"{title}-{path_date}归档"
    return f"{meeting_date} - {title}" if meeting_date else title


def mapping_source_path(key: str) -> Path | None:
    if key.startswith("backfill:"):
        return Path(key.removeprefix("backfill:"))
    if key.startswith("/"):
        return Path(key)
    return None


def scan_minutes(root: Path) -> dict[str, dict[str, str]]:
    result: dict[str, dict[str, str]] = {}
    for path in sorted(root.rglob("*.md")):
        try:
            markdown = path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            continue
        result[str(path)] = {
            "meeting_date": markdown_field(markdown, "会议日期") or date_from_path(path),
            "title": markdown_title(markdown, path.stem),
            "expected_document_name": expected_document_name(path, markdown),
        }
    return result


def audit(mapping: dict[str, Any], minutes: dict[str, dict[str, str]]) -> dict[str, Any]:
    issues: list[dict[str, Any]] = []
    by_document_name: dict[str, list[dict[str, str]]] = {}

    for key, value in mapping.items():
        if not isinstance(value, dict):
            issues.append({"severity": "error", "type": "invalid_mapping_value", "key": key})
            continue

        document_name = str(value.get("document_name") or "")
        document_id = str(value.get("document_id") or "")
        meeting_date = str(value.get("meeting_date") or "")
        source_path = mapping_source_path(key)
        expected = ""
        source_exists = None
        if source_path:
            source_exists = source_path.exists()
            minute_meta = minutes.get(str(source_path))
            if minute_meta:
                expected = minute_meta["expected_document_name"]
                if meeting_date and minute_meta["meeting_date"] and meeting_date != minute_meta["meeting_date"]:
                    issues.append(
                        {
                            "severity": "error",
                            "type": "meeting_date_mismatch",
                            "key": key,
                            "mapping_date": meeting_date,
                            "source_date": minute_meta["meeting_date"],
                        }
                    )
                if document_name and expected and document_name != expected:
                    issues.append(
                        {
                            "severity": "warning",
                            "type": "document_name_mismatch",
                            "key": key,
                            "document_name": document_name,
                            "expected_document_name": expected,
                        }
                    )
            elif source_exists is False:
                issues.append({"severity": "warning", "type": "source_file_missing", "key": key, "path": str(source_path)})

        if document_name:
            by_document_name.setdefault(document_name, []).append(
                {"key": key, "document_id": document_id, "expected_document_name": expected}
            )

    for document_name, entries in sorted(by_document_name.items()):
        document_ids = sorted({entry["document_id"] for entry in entries if entry["document_id"]})
        if len(entries) > 1 and len(document_ids) > 1:
            issues.append(
                {
                    "severity": "warning",
                    "type": "duplicate_document_name",
                    "document_name": document_name,
                    "count": len(entries),
                    "document_ids": document_ids,
                    "keys": [entry["key"] for entry in entries],
                }
            )

    return {
        "ok": not any(issue["severity"] == "error" for issue in issues),
        "mapping_count": len(mapping),
        "minutes_count": len(minutes),
        "issue_count": len(issues),
        "issues": issues,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="审计 Dify 会议纪要知识库映射和 Obsidian 正式归档的一致性")
    parser.add_argument("--mapping", default=str(DEFAULT_MAPPING_PATH), help="Dify 文档映射 JSON")
    parser.add_argument("--minutes-dir", default=str(DEFAULT_MINUTES_DIR), help="Obsidian 正式会议纪要目录")
    parser.add_argument("--json", action="store_true", help="输出 JSON")
    args = parser.parse_args()

    mapping_path = Path(args.mapping).expanduser()
    minutes_dir = Path(args.minutes_dir).expanduser()
    result = audit(read_json(mapping_path), scan_minutes(minutes_dir))
    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        print(f"映射条目: {result['mapping_count']}")
        print(f"正式纪要: {result['minutes_count']}")
        print(f"问题数量: {result['issue_count']}")
        for issue in result["issues"]:
            print(f"- [{issue['severity']}] {issue['type']}: {json.dumps(issue, ensure_ascii=False)}")
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
