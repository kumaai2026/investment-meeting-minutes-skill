#!/usr/bin/env python3
"""
Update the Obsidian investment-workflow vault to Google Drive.
"""

from __future__ import annotations

import argparse
import fcntl
import os
import shutil
import subprocess
import sys
from datetime import datetime
from pathlib import Path

DEFAULT_LOCAL_DIR = Path("/Users/kumaai/Documents/Codex/workspace/投资纪要工作流")
DEFAULT_REMOTE_DIR = "gdrive:投资纪要工作流存档/投资纪要工作流"
DEFAULT_LOG_DIR = Path("/Users/kumaai/Library/Logs/kumaai-sync")


def run_sync(local_dir: Path, remote_dir: str, log_file: Path) -> tuple[bool, str]:
    if not local_dir.exists():
        return False, f"本地 Obsidian 目录不存在: {local_dir}"

    log_file.parent.mkdir(parents=True, exist_ok=True)
    lock_file = log_file.with_suffix(".lock")
    lock_handle = lock_file.open("w", encoding="utf-8")
    try:
        fcntl.flock(lock_handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        return True, "Google Drive 同步已在后台运行"

    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    rclone = shutil.which("rclone") or "/Users/kumaai/.local/bin/rclone"
    if not Path(rclone).exists():
        return False, "未找到 rclone，请先安装或恢复 rclone 配置"

    env = os.environ.copy()
    env["PATH"] = "/Users/kumaai/.local/bin:/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin"

    command = [
        rclone,
        "copy",
        str(local_dir),
        remote_dir,
        "--create-empty-src-dirs",
        "--fast-list",
        "--exclude",
        ".DS_Store",
        "--exclude",
        "._*",
        "--exclude",
        ".~*",
        "--exclude",
        "~$*",
        "--exclude",
        ".git/**",
        "--exclude",
        ".transcribe-venv/**",
        "--exclude",
        "**/.git/**",
        "--exclude",
        "**/__pycache__/**",
        "--exclude",
        "**/*.pyc",
        "--exclude",
        "**/node_modules/**",
        "--exclude",
        "**/.meeting-minutes-internal/**",
        "--exclude",
        "**/*_analysis_ledger.json",
        "--exclude",
        "**/*_qa_report.json",
        "--log-file",
        str(log_file),
        "--log-level",
        "INFO",
        "--stats",
        "0",
    ]

    with log_file.open("a", encoding="utf-8") as handle:
        handle.write(f"\n{timestamp} sync start: {local_dir} -> {remote_dir}\n")

    try:
        result = subprocess.run(command, text=True, capture_output=True, timeout=900, env=env)
    except FileNotFoundError:
        return False, "未找到 rclone，请先安装或恢复 rclone 配置"
    except subprocess.TimeoutExpired:
        return False, "Google Drive 同步超时，已保留本地导出文件"

    with log_file.open("a", encoding="utf-8") as handle:
        if result.stdout:
            handle.write(result.stdout)
        if result.stderr:
            handle.write(result.stderr)
        handle.write(f"{timestamp} sync exit code: {result.returncode}\n")

    if result.returncode != 0:
        detail = (result.stderr or result.stdout or "未知错误").strip().splitlines()
        return False, detail[-1] if detail else "Google Drive 同步失败"

    return True, f"已同步到 {remote_dir}"


def main() -> int:
    parser = argparse.ArgumentParser(description="同步 Obsidian 投资纪要工作流到 Google Drive")
    parser.add_argument("--local-dir", default=str(DEFAULT_LOCAL_DIR), help=f"本地目录，默认 {DEFAULT_LOCAL_DIR}")
    parser.add_argument("--remote-dir", default=DEFAULT_REMOTE_DIR, help=f"rclone 远端目录，默认 {DEFAULT_REMOTE_DIR}")
    parser.add_argument(
        "--log-file",
        default=str(DEFAULT_LOG_DIR / "investment-workflow-rclone.log"),
        help="同步日志文件",
    )
    args = parser.parse_args()

    ok, message = run_sync(
        Path(args.local_dir).expanduser().resolve(),
        args.remote_dir,
        Path(args.log_file).expanduser().resolve(),
    )
    print(message)
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
