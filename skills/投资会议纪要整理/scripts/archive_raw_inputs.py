#!/usr/bin/env python3
"""
Copy raw meeting input files into the dated investment-meeting inbox archive.
"""

from __future__ import annotations

import argparse
import re
import shutil
import sys
from datetime import datetime
from pathlib import Path

DEFAULT_ARCHIVE_ROOT = Path("/Users/kumaai/Documents/Codex/workspace/投资纪要工作流/00 Inbox/会议原始记录")
INVALID_FILENAME_CHARS = r'[\\/:*?"<>|]+'
TYPE_LABELS = {
    ".docx": "文稿",
    ".doc": "文稿",
    ".txt": "文稿",
    ".md": "文稿",
    ".pdf": "文稿",
    ".mp3": "录音",
    ".m4a": "录音",
    ".wav": "录音",
    ".aac": "录音",
    ".flac": "录音",
    ".ogg": "录音",
    ".mp4": "录像",
    ".mov": "录像",
}


def sanitize_filename(value: str, *, fallback: str = "未命名会议", max_length: int = 80) -> str:
    cleaned = re.sub(INVALID_FILENAME_CHARS, "-", value or "").strip()
    cleaned = re.sub(r"\s+", " ", cleaned)
    cleaned = cleaned.strip(". ")
    if not cleaned:
        cleaned = fallback
    return cleaned[:max_length].rstrip(". ")


def material_label(path: Path) -> str:
    return TYPE_LABELS.get(path.suffix.lower(), "附件")


def standardized_filename(source: Path, archive_date: str, index: int, meeting_title: str | None) -> str:
    title = sanitize_filename(meeting_title or source.stem)
    label = material_label(source)
    return f"{archive_date} - {title} - 原始{index:02d}-{label}{source.suffix.lower()}"


def meeting_folder_name(archive_date: str, meeting_title: str | None) -> str:
    title = sanitize_filename(meeting_title)
    return f"{archive_date} - {title}"


def infer_meeting_title(files: list[Path]) -> str | None:
    for source in files:
        suffix = source.suffix.lower()
        if suffix == ".docx":
            try:
                from docx import Document  # type: ignore

                doc = Document(source)
                for paragraph in doc.paragraphs:
                    text = paragraph.text.strip()
                    if text:
                        return text
            except Exception:
                continue
        if suffix in {".txt", ".md"}:
            try:
                for line in source.read_text(encoding="utf-8").splitlines():
                    text = line.strip().lstrip("#").strip()
                    if text:
                        return text
            except Exception:
                continue
    return None


def unique_target_path(target_dir: Path, filename: str) -> Path:
    target = target_dir / filename
    if not target.exists():
        return target

    stem = target.stem
    suffix = target.suffix
    timestamp = datetime.now().strftime("%H%M%S")
    candidate = target_dir / f"{stem}-{timestamp}{suffix}"
    counter = 2
    while candidate.exists():
        candidate = target_dir / f"{stem}-{timestamp}-{counter}{suffix}"
        counter += 1
    return candidate


def archive_files(
    files: list[Path],
    archive_root: Path,
    archive_date: str,
    meeting_title: str | None = None,
) -> list[Path]:
    resolved_files = [source.expanduser().resolve() for source in files]
    resolved_title = meeting_title or infer_meeting_title(resolved_files)
    if not resolved_title and resolved_files:
        resolved_title = resolved_files[0].stem
    target_dir = archive_root / archive_date / meeting_folder_name(archive_date, resolved_title)
    target_dir.mkdir(parents=True, exist_ok=True)

    copied: list[Path] = []
    for index, resolved in enumerate(resolved_files, 1):
        if not resolved.exists():
            raise FileNotFoundError(f"输入文件不存在: {resolved}")
        if not resolved.is_file():
            raise IsADirectoryError(f"输入路径不是文件: {resolved}")

        target_name = standardized_filename(resolved, archive_date, index, resolved_title)
        target = unique_target_path(target_dir, target_name)
        shutil.copy2(resolved, target)
        copied.append(target)
    return copied


def main() -> int:
    parser = argparse.ArgumentParser(description="按日期归档投资会议原始文件")
    parser.add_argument("files", nargs="+", help="用于整理会议纪要的原始文件")
    parser.add_argument("--archive-root", default=str(DEFAULT_ARCHIVE_ROOT), help=f"归档根目录，默认 {DEFAULT_ARCHIVE_ROOT}")
    parser.add_argument("--date", default=datetime.now().strftime("%Y-%m-%d"), help="归档日期，格式 YYYY-MM-DD")
    parser.add_argument("--title", help="会议标题，用于生成规范归档文件名")
    args = parser.parse_args()

    try:
        copied = archive_files(
            [Path(item) for item in args.files],
            Path(args.archive_root).expanduser().resolve(),
            args.date,
            args.title,
        )
    except Exception as exc:
        print(f"归档失败: {exc}", file=sys.stderr)
        return 1

    for path in copied:
        print(path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
