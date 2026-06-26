#!/usr/bin/env python3
"""Sync confirmed meeting minutes into the local Dify knowledge base."""

from __future__ import annotations

import argparse
import json
import os
import re
import shlex
import sys
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

DEFAULT_CONFIG_PATH = Path("/Users/kumaai/Library/Application Support/kumaai-sync/dify-meeting-minutes.env")
DEFAULT_DIFY_API_BASE = "http://localhost:18081/v1"
DEFAULT_DATASET_NAME = "会议纪要整理知识库"
DEFAULT_MAPPING_PATH = Path(
    "/Users/kumaai/Library/Application Support/kumaai-sync/meeting-minutes-review/dify_dataset_documents.json"
)


class DifyDatasetError(RuntimeError):
    pass


@dataclass
class DifyConfig:
    api_base: str
    api_key: str
    dataset_id: str
    dataset_name: str


@dataclass
class MinuteMetadata:
    note_key: str
    document_name: str
    meeting_date: str
    meeting_type: str
    meeting_series: str
    title: str
    input_source: str
    markdown_path: str
    word_path: str
    symbols: list[str]
    doubt_count: int
    confirmed_at: str


@dataclass
class SyncResult:
    ok: bool
    action: str
    dataset_id: str
    document_id: str | None
    document_name: str
    message: str


def load_env_file(path: Path) -> dict[str, str]:
    if not path.exists():
        return {}
    values: dict[str, str] = {}
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip()
        if not key:
            continue
        try:
            values[key] = shlex.split(value)[0] if value else ""
        except ValueError:
            values[key] = value.strip("'\"")
    return values


def load_config(config_path: Path = DEFAULT_CONFIG_PATH) -> DifyConfig:
    file_values = load_env_file(config_path)
    api_base = os.environ.get("DIFY_DATASET_API_BASE") or file_values.get("DIFY_DATASET_API_BASE") or DEFAULT_DIFY_API_BASE
    api_key = os.environ.get("DIFY_DATASET_API_KEY") or file_values.get("DIFY_DATASET_API_KEY") or ""
    dataset_id = os.environ.get("DIFY_MEETING_MINUTES_DATASET_ID") or file_values.get("DIFY_MEETING_MINUTES_DATASET_ID") or ""
    dataset_name = (
        os.environ.get("DIFY_MEETING_MINUTES_DATASET_NAME")
        or file_values.get("DIFY_MEETING_MINUTES_DATASET_NAME")
        or DEFAULT_DATASET_NAME
    )
    if not api_key:
        raise DifyDatasetError(f"缺少 Dify Dataset API Key，请配置 {config_path}")
    if not dataset_id:
        raise DifyDatasetError(f"缺少 Dify 会议纪要知识库 dataset id，请配置 {config_path}")
    return DifyConfig(api_base=api_base.rstrip("/"), api_key=api_key, dataset_id=dataset_id, dataset_name=dataset_name)


def mapping_path_from_config(config_path: Path = DEFAULT_CONFIG_PATH) -> Path:
    file_values = load_env_file(config_path)
    configured = os.environ.get("MEETING_DIFY_MAPPING_PATH") or file_values.get("MEETING_DIFY_MAPPING_PATH")
    return Path(configured).expanduser() if configured else DEFAULT_MAPPING_PATH


def request_json(config: DifyConfig, method: str, path: str, payload: dict[str, Any] | None = None) -> dict[str, Any]:
    data = None
    headers = {
        "Authorization": f"Bearer {config.api_key}",
        "Content-Type": "application/json; charset=utf-8",
    }
    if payload is not None:
        data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    request = urllib.request.Request(f"{config.api_base}{path}", data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(request, timeout=60) as response:
            body = response.read().decode("utf-8")
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        raise DifyDatasetError(f"Dify API {method} {path} 失败: HTTP {exc.code}: {detail}") from exc
    except urllib.error.URLError as exc:
        raise DifyDatasetError(f"Dify API {method} {path} 连接失败: {exc}") from exc
    if not body:
        return {}
    return json.loads(body)


def markdown_title(markdown: str, fallback: str) -> str:
    for line in markdown.splitlines():
        stripped = line.strip()
        if stripped.startswith("# "):
            return stripped[2:].strip() or fallback
    return fallback


def markdown_field(markdown: str, field: str, fallback: str = "") -> str:
    pattern = re.compile(rf"^\*\*{re.escape(field)}\*\*[:：]\s*(.+?)\s*$", re.MULTILINE)
    match = pattern.search(markdown)
    return match.group(1).strip() if match else fallback


def normalize_date(value: str | None) -> str:
    raw = (value or "").strip()
    if raw:
        try:
            return datetime.strptime(raw, "%Y-%m-%d").strftime("%Y-%m-%d")
        except ValueError:
            pass
    return datetime.now().strftime("%Y-%m-%d")


def sanitize_document_name(name: str) -> str:
    cleaned = re.sub(r'[\\/:*?"<>|]+', "-", name).strip()
    cleaned = re.sub(r"\s+", " ", cleaned)
    return cleaned or "投资会议纪要"


def title_from_output_path(path_value: str) -> str:
    if not path_value:
        return ""
    stem = Path(path_value).expanduser().stem.strip()
    if not stem:
        return ""
    stem = re.sub(r"^20\d{2}-\d{2}-\d{2}\s*-\s*", "", stem).strip()
    return sanitize_document_name(stem)


def resolve_document_title(resolved_title: str, markdown_path: str, source_file: Path | None) -> str:
    generic_titles = {"投资会议纪要", "会议纪要"}
    title = sanitize_document_name(resolved_title)
    if title not in generic_titles:
        return title
    path_title = title_from_output_path(markdown_path)
    if path_title and path_title not in generic_titles:
        return path_title
    if source_file:
        source_title = title_from_output_path(str(source_file))
        if source_title and source_title not in generic_titles:
            return source_title
    return title


def date_from_path(path_value: str) -> str:
    match = re.search(r"20\d{2}-\d{2}-\d{2}", path_value)
    return match.group(0) if match else ""


def disambiguate_generic_title(title: str, resolved_date: str, markdown_path: str, source_file: Path | None) -> str:
    if title not in {"投资会议纪要", "会议纪要"}:
        return title
    path_date = date_from_path(markdown_path or (str(source_file) if source_file else ""))
    if path_date and resolved_date and path_date != resolved_date:
        return sanitize_document_name(f"{title}-{path_date}归档")
    return title


def extract_symbols(markdown: str) -> list[str]:
    symbols: set[str] = set()
    for match in re.finditer(r"【[^】]*?｜([^】]+?)】", markdown):
        target = match.group(1).strip()
        if target and target != "-":
            symbols.add(target)
    for match in re.finditer(r"\b\d{6}\.(?:SH|SZ|BJ)\b|\b\d{4,5}\.HK\b|\b[A-Z]{1,6}\b", markdown):
        symbols.add(match.group(0))
    return sorted(symbols)


def count_doubts(markdown: str) -> int:
    section_match = re.search(r"## 二、存疑与待确认(?P<body>.*)$", markdown, re.S)
    table_count = 0
    if section_match:
        for line in section_match.group("body").splitlines():
            stripped = line.strip()
            if stripped.startswith("|") and not re.fullmatch(r"\|?\s*:?-+:?\s*(\|\s*:?-+:?\s*)+\|?", stripped):
                if "原始表述" not in stripped:
                    table_count += 1
    bold_count = len(re.findall(r"\*\*[^*\n]+?\*\*", markdown))
    return max(table_count, bold_count)


def build_metadata(
    markdown: str,
    *,
    source_file: Path | None = None,
    meeting_date: str | None = None,
    meeting_type: str | None = None,
    meeting_series: str | None = None,
    title: str | None = None,
    markdown_path: str = "",
    word_path: str = "",
    note_key: str | None = None,
) -> MinuteMetadata:
    raw_title = title or markdown_title(markdown, source_file.stem if source_file else "投资会议纪要")
    resolved_title = resolve_document_title(raw_title, markdown_path, source_file)
    resolved_date = normalize_date(meeting_date or markdown_field(markdown, "会议日期"))
    resolved_title = disambiguate_generic_title(resolved_title, resolved_date, markdown_path, source_file)
    resolved_type = meeting_type or markdown_field(markdown, "会议类型", "多人复盘会")
    resolved_series = meeting_series or markdown_field(markdown, "会议系列", "未分组")
    input_source = markdown_field(markdown, "输入来源", "未注明")
    document_name = sanitize_document_name(f"{resolved_date} - {resolved_title}")
    key = note_key or f"{resolved_date}|{document_name}"
    return MinuteMetadata(
        note_key=key,
        document_name=document_name,
        meeting_date=resolved_date,
        meeting_type=resolved_type,
        meeting_series=resolved_series,
        title=resolved_title,
        input_source=input_source,
        markdown_path=markdown_path,
        word_path=word_path,
        symbols=extract_symbols(markdown),
        doubt_count=count_doubts(markdown),
        confirmed_at=datetime.now().isoformat(timespec="seconds"),
    )


def knowledge_text(markdown: str, metadata: MinuteMetadata) -> str:
    meta = {
        "meeting_date": metadata.meeting_date,
        "meeting_type": metadata.meeting_type,
        "meeting_series": metadata.meeting_series,
        "title": metadata.title,
        "input_source": metadata.input_source,
        "markdown_path": metadata.markdown_path,
        "word_path": metadata.word_path,
        "symbols": metadata.symbols,
        "doubt_count": metadata.doubt_count,
        "confirmed_at": metadata.confirmed_at,
    }
    return (
        "# 会议纪要知识库归档\n\n"
        "```json\n"
        f"{json.dumps(meta, ensure_ascii=False, indent=2)}\n"
        "```\n\n"
        "---\n\n"
        f"{markdown.strip()}\n"
    )


def load_mapping(path: Path = DEFAULT_MAPPING_PATH) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {}


def save_mapping(mapping: dict[str, Any], path: Path = DEFAULT_MAPPING_PATH) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(mapping, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def find_document_id(config: DifyConfig, metadata: MinuteMetadata, mapping: dict[str, Any]) -> str | None:
    mapped = mapping.get(metadata.note_key)
    if isinstance(mapped, dict) and mapped.get("document_id"):
        return str(mapped["document_id"])

    query = urllib.parse.urlencode({"keyword": metadata.document_name, "limit": 20})
    response = request_json(config, "GET", f"/datasets/{config.dataset_id}/documents?{query}")
    for item in response.get("data", []):
        if item.get("name") == metadata.document_name and item.get("archived") is not True:
            return str(item.get("id"))
    return None


def sync_markdown_to_dify(
    markdown: str,
    metadata: MinuteMetadata,
    *,
    config: DifyConfig | None = None,
    mapping_path: Path = DEFAULT_MAPPING_PATH,
) -> SyncResult:
    config = config or load_config()
    mapping = load_mapping(mapping_path)
    document_id = find_document_id(config, metadata, mapping)
    text = knowledge_text(markdown, metadata)
    payload: dict[str, Any] = {
        "name": metadata.document_name,
        "text": text,
        "doc_form": "text_model",
        "doc_language": "Chinese",
        "process_rule": {"mode": "automatic"},
    }
    if document_id:
        response = request_json(
            config,
            "POST",
            f"/datasets/{config.dataset_id}/documents/{document_id}/update-by-text",
            payload,
        )
        action = "updated"
    else:
        payload["indexing_technique"] = "economy"
        response = request_json(config, "POST", f"/datasets/{config.dataset_id}/document/create-by-text", payload)
        action = "created"

    document = response.get("document") or {}
    document_id = str(document.get("id") or document_id or "")
    if document_id:
        mapping[metadata.note_key] = {
            "dataset_id": config.dataset_id,
            "document_id": document_id,
            "document_name": metadata.document_name,
            "meeting_date": metadata.meeting_date,
            "meeting_type": metadata.meeting_type,
            "meeting_series": metadata.meeting_series,
            "updated_at": metadata.confirmed_at,
        }
        save_mapping(mapping, mapping_path)
    return SyncResult(
        ok=bool(document_id),
        action=action,
        dataset_id=config.dataset_id,
        document_id=document_id or None,
        document_name=metadata.document_name,
        message=f"Dify 知识库已{('更新' if action == 'updated' else '写入')}: {metadata.document_name}",
    )


def main() -> int:
    parser = argparse.ArgumentParser(description="将人工确认后的会议纪要写入 Dify 会议纪要整理知识库")
    parser.add_argument("markdown_file", help="最终确认稿 Markdown 文件")
    parser.add_argument("--meeting-date", help="会议日期 YYYY-MM-DD")
    parser.add_argument("--title", help="覆盖文档标题")
    parser.add_argument("--markdown-path", default="", help="最终 Markdown 路径")
    parser.add_argument("--word-path", default="", help="最终 Word 路径")
    parser.add_argument("--note-key", help="稳定笔记键，用于更新同一篇知识库文档")
    parser.add_argument("--config", default=str(DEFAULT_CONFIG_PATH), help="本地 Dify 知识库配置文件")
    parser.add_argument("--mapping", default=str(mapping_path_from_config()), help="本地 Dify 文档映射文件")
    parser.add_argument("--json", action="store_true", help="输出 JSON")
    args = parser.parse_args()

    source = Path(args.markdown_file).expanduser().resolve()
    if not source.exists():
        print(f"输入文件不存在: {source}", file=sys.stderr)
        return 1
    markdown = source.read_text(encoding="utf-8")
    metadata = build_metadata(
        markdown,
        source_file=source,
        meeting_date=args.meeting_date,
        title=args.title,
        markdown_path=args.markdown_path or str(source),
        word_path=args.word_path,
        note_key=args.note_key,
    )
    try:
        result = sync_markdown_to_dify(
            markdown,
            metadata,
            config=load_config(Path(args.config).expanduser()),
            mapping_path=Path(args.mapping).expanduser(),
        )
    except Exception as exc:
        if args.json:
            print(json.dumps({"ok": False, "error": str(exc)}, ensure_ascii=False))
        else:
            print(f"Dify 知识库同步失败: {exc}", file=sys.stderr)
        return 1

    payload = {
        "ok": result.ok,
        "action": result.action,
        "dataset_id": result.dataset_id,
        "document_id": result.document_id,
        "document_name": result.document_name,
        "message": result.message,
    }
    if args.json:
        print(json.dumps(payload, ensure_ascii=False))
    else:
        print(result.message)
    return 0 if result.ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
