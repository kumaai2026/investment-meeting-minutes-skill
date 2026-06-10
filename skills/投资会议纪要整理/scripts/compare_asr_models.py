#!/usr/bin/env python3
"""Compare SenseVoice primary transcription with Fun-ASR-Nano-2512 on a local clip."""

from __future__ import annotations

import argparse
import difflib
import json
import os
import subprocess
import sys
from pathlib import Path


SCRIPT_DIR = Path(__file__).resolve().parent
TRANSCRIBE_SCRIPT = SCRIPT_DIR / "transcribe_audio.py"
DEFAULT_OUTPUT_DIR = Path("/tmp/investment-meeting-asr-compare")
DEFAULT_HOTWORDS = (
    "半导体,算力,AI眼镜,液冷,CPO,PCB,光模块,光芯片,东田微,依米康,"
    "信测标准,中芯国际,中微公司,工业富联,北方华创,中际旭创,胜蓝股份"
)


def run_command(command: list[str], *, env: dict[str, str] | None = None) -> None:
    completed = subprocess.run(command, text=True, env=env, check=False)
    if completed.returncode != 0:
        raise SystemExit(completed.returncode)


def read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8", errors="replace").strip()


def write_diff(left_name: str, left: str, right_name: str, right: str, output_path: Path) -> None:
    diff = difflib.unified_diff(
        left.splitlines() or [left],
        right.splitlines() or [right],
        fromfile=left_name,
        tofile=right_name,
        lineterm="",
    )
    output_path.write_text("\n".join(diff).strip() + "\n", encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description="Compare SenseVoice and Fun-ASR-Nano-2512")
    parser.add_argument("input_file")
    parser.add_argument("--output-dir", default=str(DEFAULT_OUTPUT_DIR))
    parser.add_argument("--start", default="0")
    parser.add_argument("--seconds", type=int, default=90)
    parser.add_argument("--hotwords", default=DEFAULT_HOTWORDS)
    parser.add_argument("--nano-hub", default="ms", choices=["ms", "hf"])
    args = parser.parse_args()

    source = Path(args.input_file).expanduser().resolve()
    if not source.exists():
        print(f"输入文件不存在: {source}", file=sys.stderr)
        return 1

    output_dir = Path(args.output_dir).expanduser().resolve()
    clip_dir = output_dir / "clips"
    sensevoice_dir = output_dir / "sensevoice"
    nano_dir = output_dir / "fun-asr-nano"
    for path in (clip_dir, sensevoice_dir, nano_dir):
        path.mkdir(parents=True, exist_ok=True)

    clip_path = clip_dir / f"{source.stem}-{args.start}-{args.seconds}s.wav"
    run_command(
        [
            "ffmpeg",
            "-y",
            "-ss",
            str(args.start),
            "-t",
            str(args.seconds),
            "-i",
            str(source),
            "-ac",
            "1",
            "-ar",
            "16000",
            str(clip_path),
        ]
    )

    env = {**os.environ, "PYTHONUTF8": "1", "PYTHONIOENCODING": "utf-8"}
    run_command(
        [
            sys.executable,
            str(TRANSCRIBE_SCRIPT),
            str(clip_path),
            "--engine",
            "sensevoice",
            "--output-dir",
            str(sensevoice_dir),
            "--output-format",
            "txt",
            "--language",
            "zh",
        ],
        env=env,
    )
    run_command(
        [
            sys.executable,
            str(TRANSCRIBE_SCRIPT),
            str(clip_path),
            "--engine",
            "fun-asr-nano",
            "--output-dir",
            str(nano_dir),
            "--output-format",
            "txt",
            "--language",
            "中文",
            "--nano-hub",
            args.nano_hub,
            "--hotwords",
            args.hotwords,
        ],
        env=env,
    )

    sensevoice_text_path = sensevoice_dir / f"{clip_path.stem}.txt"
    nano_text_path = nano_dir / f"{clip_path.stem}.txt"
    sensevoice_text = read_text(sensevoice_text_path)
    nano_text = read_text(nano_text_path)
    diff_path = output_dir / f"{clip_path.stem}.sensevoice_vs_fun-asr-nano.diff"
    report_path = output_dir / f"{clip_path.stem}.comparison_report.json"
    write_diff("sensevoice", sensevoice_text, "fun-asr-nano", nano_text, diff_path)
    report_path.write_text(
        json.dumps(
            {
                "source": str(source),
                "clip": str(clip_path),
                "seconds": args.seconds,
                "sensevoice_text": str(sensevoice_text_path),
                "fun_asr_nano_text": str(nano_text_path),
                "diff": str(diff_path),
            },
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    print(f"对比完成: {report_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
