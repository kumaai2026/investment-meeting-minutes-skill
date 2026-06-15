#!/usr/bin/env python3
"""Validate the current meeting-minutes Markdown output contract."""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any

REQUIRED_SECTIONS = [
    "## 一、逐发言人原文整理",
    "## 二、存疑与待确认",
]

REQUIRED_METADATA_FIELDS = ["会议日期", "整理时间", "会议标题", "会议类型"]
METADATA_BOLD_LABELS = {
    "会议日期",
    "整理时间",
    "会议标题",
    "会议类型",
    "会议系列",
    "会议标的",
}

FORBIDDEN_PATTERNS = [
    r"AI结构化总结",
    r"标的汇总表",
    r"##\s*三[、.．]",
    r"##\s*四[、.．]",
    r"处理说明",
    r"(?m)^\*\*输入来源\*\*[:：]",
    r"(?m)^\*\*整理说明\*\*[:：]",
    r"Tool Call",
    r"skill_name",
    r"Traceback",
    r"Observation:",
]


def metadata_field_present(markdown: str, field: str) -> bool:
    return bool(re.search(rf"^\*\*{re.escape(field)}\*\*[:：]\s*\S+", markdown, re.MULTILINE))


def body_bold_terms_missing_timestamps(markdown: str) -> list[str]:
    body_match = re.search(
        r"## 一、逐发言人原文整理(?P<body>.*?)(?=^## 二、存疑与待确认)",
        markdown,
        re.S | re.M,
    )
    if not body_match:
        return []
    missing: list[str] = []
    for line in body_match.group("body").splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        if re.match(r"^\*\*(Q|q|提问|问)[:：]", stripped):
            continue
        for match in re.finditer(r"\*\*([^*\n]{1,120})\*\*", stripped):
            term = match.group(1).strip()
            if not term or term in METADATA_BOLD_LABELS:
                continue
            following = stripped[match.end() : match.end() + 40]
            if not re.match(r"^（存疑时间戳：[^）]+）", following):
                missing.append(term)
    return missing


def validate_contract(markdown: str, *, required_terms: list[str] | None = None) -> dict[str, Any]:
    errors: list[str] = []
    warnings: list[str] = []

    stripped = markdown.lstrip()
    if not stripped.startswith("# "):
        errors.append("Markdown 必须以一级标题开头")
    elif not re.search(r"(?m)^# 投资会议纪要(?:\s|｜|$)", stripped):
        errors.append("一级标题必须以 # 投资会议纪要 开头")

    for field in REQUIRED_METADATA_FIELDS:
        if not metadata_field_present(markdown, field):
            errors.append(f"缺少会议元信息字段: {field}")

    positions: list[int] = []
    for section in REQUIRED_SECTIONS:
        position = markdown.find(section)
        if position < 0:
            errors.append(f"缺少必需章节: {section}")
        positions.append(position)
    if all(position >= 0 for position in positions) and positions != sorted(positions):
        errors.append("必需章节顺序错误")

    for pattern in FORBIDDEN_PATTERNS:
        if re.search(pattern, markdown):
            errors.append(f"包含禁止输出内容: {pattern}")

    has_body_section = "## 一、逐发言人原文整理" in markdown
    has_subheading = bool(re.search(r"^###\s+", markdown, re.MULTILINE))
    has_bold_question = bool(re.search(r"^\*\*(?:Q|提问)[:：]", markdown, re.MULTILINE))
    if has_body_section and not has_subheading and not has_bold_question:
        warnings.append("逐发言人原文整理中未检测到三级发言人标题")

    ambiguity_match = re.search(r"## 二、存疑与待确认(?P<body>.*)$", markdown, re.S)
    if ambiguity_match:
        table_lines = [
            line.strip()
            for line in ambiguity_match.group("body").splitlines()
            if line.strip().startswith("|")
        ]
        if table_lines:
            headers = [cell.strip() for cell in table_lines[0].strip("|").split("|")]
            required_headers = ["时间戳", "原始表述", "当前判断", "存疑原因", "候选项", "人工确认"]
            if headers[:6] != required_headers:
                errors.append("存疑与待确认表格必须包含并按顺序使用表头: 时间戳 | 原始表述 | 当前判断 | 存疑原因 | 候选项 | 人工确认")

    missing_body_timestamps = body_bold_terms_missing_timestamps(markdown)
    if missing_body_timestamps:
        preview = "、".join(missing_body_timestamps[:8])
        errors.append(f"正文加粗存疑词后缺少存疑时间戳: {preview}")

    for term in required_terms or []:
        if term not in markdown:
            errors.append(f"缺少样例关键锚点: {term}")

    return {
        "ok": not errors,
        "errors": errors,
        "warnings": warnings,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="校验会议纪要 Markdown 是否符合当前两节输出契约")
    parser.add_argument("markdown_file", help="待校验 Markdown 文件")
    parser.add_argument("--require-term", action="append", default=[], help="必须保留的关键原文锚点，可重复")
    parser.add_argument("--json", action="store_true", help="输出 JSON")
    args = parser.parse_args()

    path = Path(args.markdown_file).expanduser()
    try:
        markdown = path.read_text(encoding="utf-8")
    except UnicodeDecodeError as exc:
        payload = {"ok": False, "errors": [f"文件不是有效 UTF-8: {exc}"], "warnings": []}
        if args.json:
            print(json.dumps(payload, ensure_ascii=False, indent=2))
        else:
            print(payload["errors"][0], file=sys.stderr)
        return 1

    result = validate_contract(markdown, required_terms=args.require_term)
    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        if result["ok"]:
            print(f"{path}: ok")
        for warning in result["warnings"]:
            print(f"warning: {warning}", file=sys.stderr)
        for error in result["errors"]:
            print(f"error: {error}", file=sys.stderr)
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
