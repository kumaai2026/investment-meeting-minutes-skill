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
    r"(?m)^##+\s*(?:摘要|投研摘要|整理者总结|投资结论|核心结论)\s*$",
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
FORBIDDEN_WORD_TEXT = [
    "AI结构化总结",
    "标的汇总表",
    "三、处理说明",
    "三、标的汇总表",
    "四、存疑与待确认",
    "输入来源",
    "整理说明",
    "#### ",
    "##### ",
]
MEETING_TYPES = {"多人复盘会", "上市公司交流", "专家交流"}
QUESTION_LINE_RE = re.compile(r"^\*\*【[^】\n]+】\*\*\s*$", re.MULTILINE)


def body_section(markdown: str) -> str:
    body_match = re.search(
        r"## 一、发言整理(?P<body>.*?)(?=^## 二、存疑与待确认|\Z)",
        markdown,
        re.S | re.M,
    )
    return body_match.group("body") if body_match else ""


def body_subheadings(markdown: str) -> list[str]:
    return re.findall(r"^###\s*(.+?)\s*$", body_section(markdown), re.MULTILINE)


def bold_question_lines(markdown: str) -> list[re.Match[str]]:
    return list(QUESTION_LINE_RE.finditer(body_section(markdown)))


def expert_questions_without_answers(markdown: str) -> list[str]:
    body = body_section(markdown)
    questions = bold_question_lines(markdown)
    findings: list[str] = []
    for index, match in enumerate(questions):
        next_start = questions[index + 1].start() if index + 1 < len(questions) else len(body)
        answer_block = body[match.end() : next_start]
        answer_lines = [
            line.strip()
            for line in answer_block.splitlines()
            if line.strip() and not line.strip().startswith("###")
        ]
        if not answer_lines:
            findings.append(match.group(0).strip())
    return findings


def validate_meeting_type_reference(markdown: str, meeting_type: str) -> list[str]:
    errors: list[str] = []
    if not meeting_type:
        return errors
    if meeting_type not in MEETING_TYPES:
        errors.append(f"会议类型只能是: {' / '.join(sorted(MEETING_TYPES))}")
        return errors

    subheadings = body_subheadings(markdown)
    questions = bold_question_lines(markdown)
    body = body_section(markdown)
    if meeting_type == "多人复盘会":
        if not subheadings:
            errors.append("多人复盘会必须按发言轮次使用三级发言人标题")
        if "标的：" in body:
            errors.append("多人复盘会小段标题不使用 标的： 前缀，应使用【标的(代码)】标题行")
        if "后半段" in body:
            errors.append("多人复盘会同一发言人再次发言时保留同名标题，不使用（后半段）")
        if "#### 【" not in body:
            errors.append("多人复盘会小段必须保留标的行；无明确标的时使用空标的行 #### 【】")
    elif meeting_type == "上市公司交流":
        title = markdown_field(markdown, "会议标题")
        if title and not title.endswith("公司交流会议"):
            errors.append("上市公司交流的会议标题应使用 XX公司交流会议")
        if not metadata_field_present(markdown, "会议标的"):
            errors.append("上市公司交流必须包含会议元信息字段: 会议标的")
        if not subheadings:
            errors.append("上市公司交流必须按实际会议环节使用三级标题")
        if re.search(r"(?m)^\s*【[^】]+】", body):
            errors.append("上市公司交流正文不使用【公司经营】【管理层回应】等额外主题标签")
        if re.search(r"(?m)^\*\*(?:Q|q|提问|问)[:：]", body):
            errors.append("上市公司交流问题格式应为 **【问题】**，不使用 Q：或提问：")
        if "标的：" in body:
            errors.append("上市公司交流正文不重复出现 标的： 行，标的信息只放在元信息")
    elif meeting_type == "专家交流":
        if not questions:
            errors.append("专家交流必须使用加粗问题格式，例如 **【问题原文】**")
        if re.search(r"(?m)^\*\*(?:Q|q|提问|问)[:：]", body):
            errors.append("专家交流问题格式应为 **【问题】**，不使用 Q：或提问：")
        missing_answers = expert_questions_without_answers(markdown)
        if missing_answers:
            preview = "；".join(missing_answers[:4])
            errors.append(f"专家交流每个问题后必须保留对应回答: {preview}")
    return errors


def metadata_field_present(markdown: str, field: str) -> bool:
    return bool(re.search(rf"^\*\*{re.escape(field)}\*\*[:：]\s*\S+", markdown, re.MULTILINE))


def markdown_field(markdown: str, field: str) -> str:
    match = re.search(rf"^\*\*{re.escape(field)}\*\*[:：]\s*(.+?)\s*$", markdown, re.MULTILINE)
    return match.group(1).strip() if match else ""


def body_bold_terms_missing_timestamps(markdown: str) -> list[str]:
    body = body_section(markdown)
    if not body:
        return []
    missing: list[str] = []
    for line in body.splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        if re.match(r"^\*\*(Q|q|提问|问)[:：]", stripped) or QUESTION_LINE_RE.match(stripped):
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
    body = body_section(markdown)
    if not body:
        return []
    terms: list[str] = []
    for line in body.splitlines():
        stripped = line.strip()
        if not stripped or re.match(r"^\*\*(Q|q|提问|问)[:：]", stripped) or QUESTION_LINE_RE.match(stripped):
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
        if re.match(r"^\*\*(Q|q|提问|问)[:：]", stripped) or QUESTION_LINE_RE.match(stripped):
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
    for match in re.finditer(r"(?m)^\|\s*未提供\s*\|", markdown):
        start = max(0, match.start() - 40)
        end = min(len(markdown), match.end() + 80)
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


def normalize_source_mode(source_mode: str | None) -> str:
    value = str(source_mode or "").strip().lower()
    if value in DOCUMENT_ONLY_SOURCE_MODES:
        return "document"
    if value in AUDIO_SOURCE_MODES:
        return "audio"
    return "auto"


def normalize_timestamp_mode(timestamp_mode: str | None, require_audio_timestamps: bool) -> str:
    if require_audio_timestamps:
        return "reliable"
    value = str(timestamp_mode or "auto").strip().lower()
    if value in {"reliable", "unavailable", "auto"}:
        return value
    return "auto"


def expected_ambiguity_headers(normalized_source_mode: str, timestamp_mode: str) -> list[list[str]]:
    if timestamp_mode == "reliable":
        return [AUDIO_AMBIGUITY_HEADER]
    if timestamp_mode == "unavailable" or normalized_source_mode == "document":
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
    timestamp_mode: str | None = "auto",
) -> dict[str, Any]:
    errors: list[str] = []
    warnings: list[str] = []
    normalized_source_mode = normalize_source_mode(source_mode)
    normalized_timestamp_mode = normalize_timestamp_mode(timestamp_mode, require_audio_timestamps)

    stripped = markdown.lstrip()
    if not stripped.startswith("# "):
        errors.append("Markdown 必须以一级标题开头")
    elif not re.search(r"(?m)^# 投资会议纪要(?:\s|｜|$)", stripped):
        errors.append("一级标题必须以 # 投资会议纪要 开头")

    for field in REQUIRED_METADATA_FIELDS:
        if not metadata_field_present(markdown, field):
            errors.append(f"缺少会议元信息字段: {field}")

    meeting_type = markdown_field(markdown, "会议类型")
    errors.extend(validate_meeting_type_reference(markdown, meeting_type))

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
    has_bold_question = bool(bold_question_lines(markdown))
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
            allowed_headers = expected_ambiguity_headers(normalized_source_mode, normalized_timestamp_mode)
            if headers not in allowed_headers:
                errors.append(f"存疑与待确认表格表头必须固定为: {format_allowed_headers(allowed_headers)}")
            if real_ambiguity_row_count(markdown, headers) == 0:
                errors.append("存疑与待确认章节存在时必须包含至少一条真实存疑；无存疑内容时应省略整节")
            manual_confirmation_rows = ambiguity_rows_with_manual_confirmation(markdown, headers)
            if manual_confirmation_rows:
                preview = "；".join(manual_confirmation_rows[:4])
                errors.append(f"人工确认列必须存在于最后且保持空白，供人工填写: {preview}")

    if normalized_source_mode == "audio" and normalized_timestamp_mode != "unavailable":
        missing_body_timestamps = body_bold_terms_missing_timestamps(markdown)
        if missing_body_timestamps:
            preview = "、".join(missing_body_timestamps[:8])
            warnings.append(f"正文加粗存疑词后建议补充存疑时间戳: {preview}")

    if normalized_source_mode == "audio" or normalized_timestamp_mode == "reliable":
        fallback_timestamps = audio_timestamp_fallbacks(markdown)
        if fallback_timestamps:
            preview = "；".join(fallback_timestamps[:4])
            errors.append(f"音频来源不允许将存疑时间戳写成未提供: {preview}")

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
        help="来源模式；需结合 --timestamp-mode 判断存疑表是否包含时间戳列",
    )
    parser.add_argument(
        "--timestamp-mode",
        choices=["auto", "reliable", "unavailable"],
        default="auto",
        help="时间戳可靠性；reliable 要求带时间戳表头，unavailable 要求无时间戳表头，auto 接受两者",
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
        timestamp_mode=args.timestamp_mode,
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
