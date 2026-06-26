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
    "## 一、发言整理",
]

REQUIRED_METADATA_FIELDS = ["会议日期", "整理时间", "会议标题", "会议类型", "会议系列"]
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
    r"(?m)^###\s*问答\s*\d+",
    r"(?im)^\s*A[:：]",
]

DOCUMENT_ONLY_SOURCE_MODES = {"document", "document-only", "text", "text-only", "文稿", "纯文本"}
AUDIO_SOURCE_MODES = {"audio", "audio-only", "audio-text", "audio+text", "音频", "音频转写", "文稿+音频"}
AUDIO_AMBIGUITY_HEADER = ["时间戳", "原始表述", "当前判断", "候选项", "人工确认"]
DOCUMENT_AMBIGUITY_HEADER = ["原始表述", "当前判断", "候选项", "人工确认"]
PLACEHOLDER_VALUES = {"", "-", "无", "暂无", "无存疑", "暂无存疑", "none", "n/a"}
REQUIRED_WORD_TEXT = ["一、发言整理"]
FORBIDDEN_WORD_TEXT = ["AI结构化总结", "标的汇总表", "三、处理说明", "三、标的汇总表", "四、存疑与待确认", "输入来源", "整理说明"]


def metadata_field_present(markdown: str, field: str) -> bool:
    return bool(re.search(rf"^\*\*{re.escape(field)}\*\*[:：]\s*\S+", markdown, re.MULTILINE))


def markdown_field(markdown: str, field: str) -> str:
    match = re.search(rf"^\*\*{re.escape(field)}\*\*[:：]\s*(.+?)\s*$", markdown, re.MULTILINE)
    return match.group(1).strip() if match else ""


def body_bold_terms_missing_timestamps(markdown: str) -> list[str]:
    body_match = re.search(
        r"## 一、发言整理(?P<body>.*?)(?=^## 二、存疑与待确认|\Z)",
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


def body_bold_terms(markdown: str) -> list[str]:
    body_match = re.search(
        r"## 一、发言整理(?P<body>.*?)(?=^## 二、存疑与待确认|\Z)",
        markdown,
        re.S | re.M,
    )
    if not body_match:
        return []
    terms: list[str] = []
    for line in body_match.group("body").splitlines():
        stripped = line.strip()
        if not stripped or re.match(r"^\*\*(Q|q|提问|问)[:：]", stripped):
            continue
        for match in re.finditer(r"\*\*([^*\n]{1,120})\*\*", stripped):
            term = match.group(1).strip()
            if term and term not in METADATA_BOLD_LABELS:
                terms.append(term)
    return terms


def markdown_bold_terms(markdown: str) -> list[str]:
    terms: list[str] = []
    for line in markdown.splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        metadata_match = re.match(r"^\*\*([^*\n：:]{1,20})\*\*[:：]", stripped)
        if metadata_match and metadata_match.group(1).strip() in METADATA_BOLD_LABELS:
            continue
        if re.match(r"^\*\*(Q|q|提问|问)[:：]", stripped):
            continue
        for match in re.finditer(r"\*\*([^*\n]{1,80})\*\*", stripped):
            term = match.group(1).strip()
            if term and term not in METADATA_BOLD_LABELS:
                terms.append(term)
    return terms


def docx_paragraph_text(path: Path) -> tuple[str, list[dict[str, Any]]]:
    try:
        from docx import Document
    except ImportError as exc:
        raise RuntimeError("缺少 python-docx，无法校验 Word 文件") from exc

    document = Document(str(path))
    paragraphs: list[str] = []
    runs: list[dict[str, Any]] = []
    for paragraph in document.paragraphs:
        paragraphs.append(paragraph.text)
        for run in paragraph.runs:
            if run.text:
                runs.append({"text": run.text, "bold": bool(run.bold), "underline": bool(run.underline)})
    for table in document.tables:
        for row in table.rows:
            for cell in row.cells:
                paragraphs.append(cell.text)
                for paragraph in cell.paragraphs:
                    for run in paragraph.runs:
                        if run.text:
                            runs.append({"text": run.text, "bold": bool(run.bold), "underline": bool(run.underline)})
    return "\n".join(paragraphs), runs


def validate_word_contract(docx_path: Path, markdown: str | None = None) -> dict[str, Any]:
    errors: list[str] = []
    warnings: list[str] = []
    if not docx_path.exists():
        return {"ok": False, "errors": [f"Word 文件不存在: {docx_path}"], "warnings": []}

    try:
        text, runs = docx_paragraph_text(docx_path)
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "errors": [f"Word 文件无法打开: {exc}"], "warnings": []}

    for required in REQUIRED_WORD_TEXT:
        if required not in text:
            errors.append(f"Word 缺少必需章节: {required}")
    for forbidden in FORBIDDEN_WORD_TEXT:
        if forbidden in text:
            errors.append(f"Word 包含禁止内容: {forbidden}")
    if not re.search(r"[\u4e00-\u9fff]", text):
        errors.append("Word 未检测到中文内容")

    if markdown:
        for term in markdown_bold_terms(markdown):
            matched = any(term in run["text"] and run["bold"] and run["underline"] for run in runs)
            if not matched:
                errors.append(f"Markdown 加粗存疑词未在 Word 中检测到加粗+下划线: {term}")

    return {
        "ok": not errors,
        "errors": errors,
        "warnings": warnings,
        "paragraph_count": text.count("\n") + 1 if text else 0,
        "run_count": len(runs),
    }


def audio_timestamp_fallbacks(markdown: str) -> list[str]:
    findings: list[str] = []
    for match in re.finditer(r"存疑时间戳：未提供", markdown):
        start = max(0, match.start() - 40)
        end = min(len(markdown), match.end() + 40)
        findings.append(re.sub(r"\s+", " ", markdown[start:end]).strip())

    return findings


def contains_timestamp_markers(markdown: str) -> list[str]:
    findings: list[str] = []
    for pattern in (r"存疑时间戳[:：]", r"(?m)^\|\s*时间戳\s*\|", r"(?m)^\|\s*(?:\d{1,2}:)?\d{1,2}:\d{2}\s*\|", r"(?m)^\|\s*未提供\s*\|"):
        for match in re.finditer(pattern, markdown):
            start = max(0, match.start() - 40)
            end = min(len(markdown), match.end() + 60)
            findings.append(re.sub(r"\s+", " ", markdown[start:end]).strip())
            if len(findings) >= 8:
                return findings
    return findings


def normalize_source_mode(source_mode: str | None, require_audio_timestamps: bool) -> str:
    value = str(source_mode or "").strip().lower()
    if value in DOCUMENT_ONLY_SOURCE_MODES:
        return "document"
    if require_audio_timestamps or value in AUDIO_SOURCE_MODES:
        return "audio"
    return "auto"


def expected_ambiguity_headers(normalized_source_mode: str) -> list[list[str]]:
    if normalized_source_mode == "audio":
        return [AUDIO_AMBIGUITY_HEADER]
    if normalized_source_mode == "document":
        return [DOCUMENT_AMBIGUITY_HEADER]
    return [AUDIO_AMBIGUITY_HEADER, DOCUMENT_AMBIGUITY_HEADER]


def format_allowed_headers(headers: list[list[str]]) -> str:
    return " 或 ".join(" | ".join(header) for header in headers)


def has_ambiguity_section(markdown: str) -> bool:
    return bool(re.search(r"^## 二、存疑与待确认\s*$", markdown, re.MULTILINE))


def ambiguity_table_lines(markdown: str) -> list[str]:
    ambiguity_match = re.search(r"## 二、存疑与待确认(?P<body>.*)$", markdown, re.S)
    if not ambiguity_match:
        return []
    return [
        line.strip()
        for line in ambiguity_match.group("body").splitlines()
        if line.strip().startswith("|")
    ]


def _is_separator_line(line: str) -> bool:
    return bool(re.match(r"^\|\s*[-:| ]+\s*$", line.strip()))


def _is_placeholder_ambiguity_row(cells: list[str], original_index: int) -> bool:
    if not cells or original_index >= len(cells):
        return True
    original = cells[original_index].strip().lower()
    return original in PLACEHOLDER_VALUES


def ambiguity_rows_with_manual_confirmation(markdown: str, headers: list[str]) -> list[str]:
    if "人工确认" not in headers:
        return ["存疑表缺少强制列: 人工确认"]
    if headers[-1] != "人工确认":
        return ["人工确认列必须是最后一列"]
    manual_index = headers.index("人工确认")
    original_index = headers.index("原始表述") if "原始表述" in headers else 0
    findings: list[str] = []
    table_lines = ambiguity_table_lines(markdown)
    for line in table_lines[2:]:
        if _is_separator_line(line):
            continue
        cells = [cell.strip() for cell in line.strip("|").split("|")]
        if _is_placeholder_ambiguity_row(cells, original_index):
            continue
        if manual_index >= len(cells):
            findings.append(line)
            continue
        if cells[manual_index].strip():
            findings.append(line)
    return findings


def real_ambiguity_row_count(markdown: str, headers: list[str]) -> int:
    original_index = headers.index("原始表述") if "原始表述" in headers else 0
    count = 0
    for line in ambiguity_table_lines(markdown)[2:]:
        if _is_separator_line(line):
            continue
        cells = [cell.strip() for cell in line.strip("|").split("|")]
        if not _is_placeholder_ambiguity_row(cells, original_index):
            count += 1
    return count


def validate_contract(
    markdown: str,
    *,
    required_terms: list[str] | None = None,
    source_mode: str | None = None,
    require_audio_timestamps: bool = False,
) -> dict[str, Any]:
    errors: list[str] = []
    warnings: list[str] = []
    normalized_source_mode = normalize_source_mode(source_mode, require_audio_timestamps)

    stripped = markdown.lstrip()
    if not stripped.startswith("# "):
        errors.append("Markdown 必须以一级标题开头")
    elif not re.search(r"(?m)^# 投资会议纪要(?:\s|｜|$)", stripped):
        errors.append("一级标题必须以 # 投资会议纪要 开头")

    for field in REQUIRED_METADATA_FIELDS:
        if not metadata_field_present(markdown, field):
            errors.append(f"缺少会议元信息字段: {field}")

    meeting_type = markdown_field(markdown, "会议类型")
    if "上市公司交流" in meeting_type and not metadata_field_present(markdown, "会议标的"):
        warnings.append("上市公司交流建议包含会议元信息字段: 会议标的")
    if "专家交流" in meeting_type and not re.search(r"^\*\*(?:Q|提问)[:：]", markdown, re.MULTILINE):
        warnings.append("专家交流正文建议使用加粗问题格式，例如 **Q：问题原文**")

    body_position = markdown.find("## 一、发言整理")
    if body_position < 0:
        errors.append("缺少必需章节: ## 一、发言整理")
    ambiguity_position = markdown.find("## 二、存疑与待确认")
    if body_position >= 0 and ambiguity_position >= 0 and body_position > ambiguity_position:
        errors.append("必需章节顺序错误")

    for pattern in FORBIDDEN_PATTERNS:
        if re.search(pattern, markdown):
            errors.append(f"包含禁止输出内容: {pattern}")

    has_body_section = "## 一、发言整理" in markdown
    has_subheading = bool(re.search(r"^###\s+", markdown, re.MULTILINE))
    has_bold_question = bool(re.search(r"^\*\*(?:Q|提问)[:：]", markdown, re.MULTILINE))
    if has_body_section and not has_subheading and not has_bold_question:
        warnings.append("发言整理中未检测到三级发言人标题")

    bold_terms = body_bold_terms(markdown)
    ambiguity_exists = has_ambiguity_section(markdown)
    if not ambiguity_exists and bold_terms:
        preview = "、".join(bold_terms[:8])
        errors.append(f"正文存在加粗存疑词但缺少 ## 二、存疑与待确认: {preview}")

    if ambiguity_exists:
        table_lines = ambiguity_table_lines(markdown)
        if not table_lines:
            errors.append("存疑与待确认章节存在时必须包含 Markdown 表格；无存疑内容时应省略整节")
        else:
            headers = [cell.strip() for cell in table_lines[0].strip("|").split("|")]
            allowed_headers = expected_ambiguity_headers(normalized_source_mode)
            if headers not in allowed_headers:
                errors.append(f"存疑与待确认表格表头必须固定为: {format_allowed_headers(allowed_headers)}")
            if real_ambiguity_row_count(markdown, headers) == 0:
                errors.append("存疑与待确认章节存在时必须包含至少一条真实存疑；无存疑内容时应省略整节")
            manual_confirmation_rows = ambiguity_rows_with_manual_confirmation(markdown, headers)
            if manual_confirmation_rows:
                preview = "；".join(manual_confirmation_rows[:4])
                errors.append(f"人工确认列必须存在于最后且保持空白，供人工填写: {preview}")

    if normalized_source_mode == "audio":
        missing_body_timestamps = body_bold_terms_missing_timestamps(markdown)
        if missing_body_timestamps:
            preview = "、".join(missing_body_timestamps[:8])
            warnings.append(f"正文加粗存疑词后建议补充存疑时间戳: {preview}")

    if require_audio_timestamps:
        fallback_timestamps = audio_timestamp_fallbacks(markdown)
        if fallback_timestamps:
            preview = "；".join(fallback_timestamps[:4])
            warnings.append(f"音频来源样例建议避免将存疑时间戳写成未提供: {preview}")

    for term in required_terms or []:
        if term not in markdown:
            errors.append(f"缺少样例关键锚点: {term}")

    return {
        "ok": not errors,
        "errors": errors,
        "warnings": warnings,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="校验会议纪要 Markdown 是否符合当前输出契约")
    parser.add_argument("markdown_file", help="待校验 Markdown 文件")
    parser.add_argument("--word", help="可选：同时校验对应导出 Word 文件")
    parser.add_argument("--require-term", action="append", default=[], help="必须保留的关键原文锚点，可重复")
    parser.add_argument(
        "--source-mode",
        choices=["auto", "document", "document-only", "text", "text-only", "audio", "audio-only", "audio-text", "audio+text"],
        default="auto",
        help="来源模式；音频来源的存疑表包含时间戳列，文稿来源不显示时间戳列",
    )
    parser.add_argument("--require-audio-timestamps", action="store_true", help="音频来源不允许把存疑时间戳批量写成未提供")
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

    result = validate_contract(
        markdown,
        required_terms=args.require_term,
        source_mode=args.source_mode,
        require_audio_timestamps=args.require_audio_timestamps,
    )
    if args.word:
        word_result = validate_word_contract(Path(args.word).expanduser(), markdown)
        result["word"] = word_result
        result["errors"].extend(word_result["errors"])
        result["warnings"].extend(word_result["warnings"])
        result["ok"] = result["ok"] and word_result["ok"]
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
