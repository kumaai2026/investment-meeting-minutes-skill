#!/usr/bin/env python3
"""High-quality local transcription wrapper for SenseVoice, Fun-ASR-Nano, and Whisper."""

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

DEFAULT_SENSEVOICE_MODEL = "iic/SenseVoiceSmall"
DEFAULT_FUNASR_NANO_MODEL = "FunAudioLLM/Fun-ASR-Nano-2512"
DEFAULT_FUNASR_NANO_HUB = "ms"
MIN_WHISPER_MODEL = "medium"
LOW_QUALITY_MODELS = {"tiny", "base", "small"}
SENSEVOICE_TEXT_FORMATS = {"txt", "json", "all"}
FUNASR_NANO_TEXT_FORMATS = {"txt", "json", "all"}


def _configure_model_cache(cache_dir: str) -> None:
    cache_value = (cache_dir or os.environ.get("FUNASR_MODEL_CACHE") or "").strip()
    if not cache_value:
        return
    root = Path(cache_value).expanduser().resolve()
    os.environ.setdefault("MODELSCOPE_CACHE", str(root / "modelscope"))
    os.environ.setdefault("HF_HOME", str(root / "huggingface"))


def _ensure_ffmpeg_in_path(env: dict[str, str]) -> dict[str, str]:
    if shutil.which("ffmpeg"):
        return env

    try:
        import imageio_ffmpeg  # type: ignore

        ffmpeg_exe = Path(imageio_ffmpeg.get_ffmpeg_exe())
        tmp_dir = Path(tempfile.mkdtemp(prefix="ffmpeg-bin-"))
        link = tmp_dir / "ffmpeg"
        if not link.exists():
            link.symlink_to(ffmpeg_exe)
        env["PATH"] = f"{tmp_dir}:{env.get('PATH', '')}"
    except Exception:
        pass

    return env


def _clean_sensevoice_text(text: str) -> str:
    """Remove SenseVoice control tags while preserving the spoken content."""
    text = re.sub(r"<\|[^|]+?\|>", "", text)
    return re.sub(r"\s+", " ", text).strip()


def _extract_funasr_text(result: object) -> str:
    chunks = result if isinstance(result, list) else [result]
    texts: list[str] = []
    for chunk in chunks:
        if isinstance(chunk, dict):
            text = str(chunk.get("text", ""))
        else:
            text = str(chunk)
        cleaned = _clean_sensevoice_text(text)
        if cleaned:
            texts.append(cleaned)
    return "\n".join(texts).strip()


def _select_device(requested: str = "auto") -> str:
    requested = (requested or "auto").strip().lower()
    if requested and requested != "auto":
        return requested
    try:
        import torch  # type: ignore

        if getattr(torch.backends, "mps", None) and torch.backends.mps.is_available():
            return "mps"
    except Exception:
        pass
    return "cpu"


def _run_sensevoice(
    input_file: Path,
    output_dir: Path,
    model_name: str,
    language: str,
    output_format: str,
) -> int:
    if output_format not in SENSEVOICE_TEXT_FORMATS:
        print(
            "SenseVoice 当前只写出 txt/json/all；如需 vtt/srt/tsv，请使用 --engine whisper。",
            file=sys.stderr,
        )
        return 2

    try:
        from funasr import AutoModel  # type: ignore
    except Exception as exc:
        print(f"缺少 SenseVoice/FunASR 依赖: {exc}", file=sys.stderr)
        return 127

    try:
        model = AutoModel(
            model=model_name,
            trust_remote_code=True,
            vad_model="fsmn-vad",
            vad_kwargs={"max_single_segment_time": 30000},
            device=_select_device("auto"),
        )
    except RuntimeError as exc:
        if model_name == DEFAULT_SENSEVOICE_MODEL and "not registered" in str(exc):
            model = AutoModel(
                model="SenseVoiceSmall",
                trust_remote_code=True,
                vad_model="fsmn-vad",
                vad_kwargs={"max_single_segment_time": 30000},
                device=_select_device("auto"),
            )
        else:
            raise
    result = model.generate(
        input=str(input_file),
        language=language,
        use_itn=True,
        batch_size_s=60,
        merge_vad=True,
        merge_length_s=15,
    )

    output_text = _extract_funasr_text(result)
    stem = input_file.stem
    if output_format in {"txt", "all"}:
        (output_dir / f"{stem}.txt").write_text(output_text + "\n", encoding="utf-8")
    if output_format in {"json", "all"}:
        payload = {
            "engine": "sensevoice",
            "model": model_name,
            "language": language,
            "input": str(input_file),
            "text": output_text,
            "raw": result,
        }
        (output_dir / f"{stem}.json").write_text(
            json.dumps(payload, ensure_ascii=False, indent=2, default=str),
            encoding="utf-8",
        )

    print(f"SenseVoice 转录完成: {output_dir / f'{stem}.txt'}")
    return 0


def _run_funasr_nano(
    input_file: Path,
    output_dir: Path,
    model_name: str,
    hub: str,
    language: str,
    output_format: str,
    hotwords: str,
    device: str,
    use_vad: bool,
) -> int:
    if output_format not in FUNASR_NANO_TEXT_FORMATS:
        print(
            "Fun-ASR-Nano 当前只写出 txt/json/all；如需 vtt/srt/tsv，请使用 --engine whisper。",
            file=sys.stderr,
        )
        return 2

    try:
        from funasr import AutoModel  # type: ignore
    except Exception as exc:
        print(f"缺少 Fun-ASR-Nano 依赖: {exc}", file=sys.stderr)
        return 127

    resolved_device = _select_device(device)
    model_kwargs: dict[str, object] = {
        "model": model_name,
        "trust_remote_code": True,
        "device": resolved_device,
        "hub": hub,
    }
    if use_vad:
        model_kwargs.update(
            {
                "vad_model": "fsmn-vad",
                "vad_kwargs": {"max_single_segment_time": 30000},
            }
        )

    model = AutoModel(**model_kwargs)
    hotword_list = [item.strip() for item in hotwords.split(",") if item.strip()]
    result = model.generate(
        input=[str(input_file)],
        cache={},
        batch_size=1,
        language=language,
        hotwords=hotword_list,
        itn=True,
    )

    output_text = _extract_funasr_text(result)
    stem = input_file.stem
    if output_format in {"txt", "all"}:
        (output_dir / f"{stem}.txt").write_text(output_text + "\n", encoding="utf-8")
    if output_format in {"json", "all"}:
        payload = {
            "engine": "fun-asr-nano",
            "model": model_name,
            "hub": hub,
            "language": language,
            "device": resolved_device,
            "hotwords": hotword_list,
            "input": str(input_file),
            "text": output_text,
            "raw": result,
        }
        (output_dir / f"{stem}.json").write_text(
            json.dumps(payload, ensure_ascii=False, indent=2, default=str),
            encoding="utf-8",
        )

    print(f"Fun-ASR-Nano 转录完成: {output_dir / f'{stem}.txt'}")
    return 0


def _run_whisper(
    input_file: Path,
    output_dir: Path,
    model: str,
    language: str,
    output_format: str,
) -> int:
    model = model.strip().lower()
    if model in LOW_QUALITY_MODELS:
        print(
            f"检测到低质量 Whisper 模型 `{model}`，已自动提升为 `{MIN_WHISPER_MODEL}`（质量优先）。",
            file=sys.stderr,
        )
        model = MIN_WHISPER_MODEL

    whisper_cmd = shutil.which("whisper")
    if whisper_cmd:
        cmd = [
            whisper_cmd,
            str(input_file),
            "--model",
            model,
            "--language",
            language,
            "--task",
            "transcribe",
            "--output_dir",
            str(output_dir),
            "--output_format",
            output_format,
        ]
    else:
        cmd = [
            sys.executable,
            "-m",
            "whisper",
            str(input_file),
            "--model",
            model,
            "--language",
            language,
            "--task",
            "transcribe",
            "--output_dir",
            str(output_dir),
            "--output_format",
            output_format,
        ]

    env = _ensure_ffmpeg_in_path(dict(os.environ))
    completed = subprocess.run(cmd, check=False, env=env)
    return completed.returncode


def main() -> int:
    parser = argparse.ArgumentParser(description="使用本地 ASR 转录音频（优先 SenseVoice，可显式运行 Fun-ASR-Nano）")
    parser.add_argument("input_file", help="音频文件路径")
    parser.add_argument(
        "--output-dir",
        default=".",
        help="转录文件输出目录，默认当前目录",
    )
    parser.add_argument(
        "--engine",
        default="auto",
        choices=["auto", "sensevoice", "fun-asr-nano", "whisper"],
        help="ASR 引擎，默认 auto（优先 SenseVoice，必要时回退 Whisper）；fun-asr-nano 用于辅助对照",
    )
    parser.add_argument(
        "--model",
        default=DEFAULT_SENSEVOICE_MODEL,
        help="SenseVoice/FunASR 模型名，默认 iic/SenseVoiceSmall",
    )
    parser.add_argument(
        "--nano-model",
        default=DEFAULT_FUNASR_NANO_MODEL,
        help="Fun-ASR-Nano 模型名，默认 FunAudioLLM/Fun-ASR-Nano-2512",
    )
    parser.add_argument(
        "--nano-hub",
        default=DEFAULT_FUNASR_NANO_HUB,
        choices=["ms", "hf"],
        help="Fun-ASR-Nano 模型源，默认 ms（ModelScope，国内网络更稳）",
    )
    parser.add_argument(
        "--hotwords",
        default="",
        help="逗号分隔热词，Fun-ASR-Nano 辅助转录时使用",
    )
    parser.add_argument(
        "--device",
        default="auto",
        help="FunASR 设备，默认 auto（macOS 优先 mps，否则 cpu）",
    )
    parser.add_argument(
        "--no-vad",
        action="store_true",
        help="Fun-ASR-Nano 不启用 fsmn-vad",
    )
    parser.add_argument(
        "--cache-dir",
        default="",
        help="可选模型缓存根目录；也可用 FUNASR_MODEL_CACHE 环境变量设置",
    )
    parser.add_argument(
        "--whisper-model",
        default=MIN_WHISPER_MODEL,
        help="Whisper 回退模型名，默认 medium（质量优先）",
    )
    parser.add_argument(
        "--output-format",
        default="txt",
        choices=["txt", "vtt", "srt", "tsv", "json", "all"],
        help="输出格式，默认 txt",
    )
    parser.add_argument(
        "--language",
        default="zh",
        help="语言，默认 zh",
    )
    args = parser.parse_args()

    input_file = Path(args.input_file).expanduser().resolve()
    if not input_file.exists():
        print(f"输入文件不存在: {input_file}", file=sys.stderr)
        return 1

    output_dir = Path(args.output_dir).expanduser().resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    _configure_model_cache(args.cache_dir)

    if args.engine in {"auto", "sensevoice"}:
        sensevoice_code = _run_sensevoice(
            input_file=input_file,
            output_dir=output_dir,
            model_name=args.model,
            language=args.language,
            output_format=args.output_format,
        )
        if sensevoice_code == 0 or args.engine == "sensevoice":
            return sensevoice_code
        print("SenseVoice 不可用，自动回退到 Whisper。", file=sys.stderr)

    if args.engine == "fun-asr-nano":
        return _run_funasr_nano(
            input_file=input_file,
            output_dir=output_dir,
            model_name=args.nano_model,
            hub=args.nano_hub,
            language=args.language,
            output_format=args.output_format,
            hotwords=args.hotwords,
            device=args.device,
            use_vad=not args.no_vad,
        )

    return _run_whisper(
        input_file=input_file,
        output_dir=output_dir,
        model=args.whisper_model,
        language=args.language,
        output_format=args.output_format,
    )


if __name__ == "__main__":
    raise SystemExit(main())
