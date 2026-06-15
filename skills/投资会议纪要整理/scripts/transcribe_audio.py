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
DEFAULT_LOCAL_CACHE = Path("/Users/nananaranja/Documents/会议纪要整理/.model-cache")
MODEL_ALIASES = {
    "iic/SenseVoiceSmall": ("modelscope", "models/iic/SenseVoiceSmall"),
    "SenseVoiceSmall": ("modelscope", "models/iic/SenseVoiceSmall"),
    "fsmn-vad": ("modelscope", "models/iic/speech_fsmn_vad_zh-cn-16k-common-pytorch"),
    "ct-punc": ("modelscope", "models/iic/punc_ct-transformer_cn-en-common-vocab471067-large"),
    "cam++": ("modelscope", "models/iic/speech_campplus_sv_zh-cn_16k-common"),
    "FunAudioLLM/Fun-ASR-Nano-2512": ("modelscope", "models/FunAudioLLM/Fun-ASR-Nano-2512"),
}
REQUIRED_MODEL_FILES = {
    "iic/SenseVoiceSmall": ("config.yaml", "model.pt"),
    "SenseVoiceSmall": ("config.yaml", "model.pt"),
    "fsmn-vad": ("config.yaml", "model.pt"),
    "ct-punc": ("config.yaml", "model.pt"),
    "cam++": ("config.yaml", "campplus_cn_common.bin"),
    "FunAudioLLM/Fun-ASR-Nano-2512": ("configuration.json",),
}
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


def _model_cache_root() -> Path | None:
    candidates = [
        os.environ.get("FUNASR_MODEL_CACHE"),
        os.environ.get("MODELSCOPE_CACHE"),
        DEFAULT_LOCAL_CACHE,
        "/Users/nananaranja/Documents/Codex/asr-model-cache",
    ]
    for value in candidates:
        if not value:
            continue
        path = Path(value).expanduser().resolve()
        if path.name == "modelscope":
            path = path.parent
        if path.exists():
            return path
    return None


def _is_complete_model_dir(path: Path, model_name: str) -> bool:
    required_files = REQUIRED_MODEL_FILES.get(model_name, ("config.yaml",))
    return path.is_dir() and all((path / item).exists() for item in required_files)


def _model_candidates(model_name: str) -> list[Path]:
    alias = MODEL_ALIASES.get(model_name)
    root = _model_cache_root()
    if not alias or not root:
        return []
    source, relative_path = alias
    candidates = [root / source / relative_path]
    if source == "modelscope" and relative_path.startswith("models/"):
        candidates.append(root / source / relative_path.removeprefix("models/"))
    return candidates


def _resolve_model_ref(model_name: str) -> str:
    path = Path(model_name).expanduser()
    if path.exists() and _is_complete_model_dir(path, model_name):
        return str(path.resolve())
    for candidate in _model_candidates(model_name):
        if _is_complete_model_dir(candidate, model_name):
            return str(candidate)
    return model_name


def _model_cache_status(model_name: str) -> dict[str, object]:
    candidates = _model_candidates(model_name)
    if not candidates:
        return {"model": model_name, "path": "", "exists": False, "complete": False, "missing": ["cache root"]}
    required_files = REQUIRED_MODEL_FILES.get(model_name, ("config.yaml",))
    candidate = next((item for item in candidates if _is_complete_model_dir(item, model_name)), candidates[0])
    missing = [item for item in required_files if not (candidate / item).exists()]
    return {
        "model": model_name,
        "path": str(candidate),
        "exists": candidate.exists(),
        "complete": candidate.exists() and not missing,
        "missing": missing,
        "checked_paths": [str(item) for item in candidates],
    }


def _model_cache_report() -> dict[str, object]:
    return {
        "cache_root": str(_model_cache_root() or ""),
        "models": {
            "sensevoice": _model_cache_status(DEFAULT_SENSEVOICE_MODEL),
            "vad": _model_cache_status("fsmn-vad"),
            "punc": _model_cache_status("ct-punc"),
            "speaker_diarization": _model_cache_status("cam++"),
            "fun_asr_nano": _model_cache_status(DEFAULT_FUNASR_NANO_MODEL),
        },
    }


def _print_model_cache_report() -> None:
    print(json.dumps(_model_cache_report(), ensure_ascii=False, indent=2))


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


def _speaker_label(value: object) -> str:
    raw = str(value if value is not None else "").strip()
    if not raw:
        return "Speaker ?"
    if raw.lower().startswith("speaker") or raw.startswith("发言人"):
        return raw
    return f"Speaker {raw}"


def _ms_to_timestamp(value: object) -> str:
    try:
        ms = int(float(value))
    except (TypeError, ValueError):
        return ""
    total_seconds, millis = divmod(max(ms, 0), 1000)
    minutes, seconds = divmod(total_seconds, 60)
    hours, minutes = divmod(minutes, 60)
    if hours:
        return f"{hours:02d}:{minutes:02d}:{seconds:02d}.{millis:03d}"
    return f"{minutes:02d}:{seconds:02d}.{millis:03d}"


def _extract_sentence_info(result: object) -> list[dict[str, object]]:
    chunks = result if isinstance(result, list) else [result]
    sentences: list[dict[str, object]] = []
    for chunk in chunks:
        if not isinstance(chunk, dict):
            continue
        for item in chunk.get("sentence_info") or []:
            if not isinstance(item, dict):
                continue
            text = _clean_sensevoice_text(str(item.get("text") or item.get("sentence") or ""))
            if not text:
                continue
            sentences.append(
                {
                    "speaker": _speaker_label(item.get("spk")),
                    "speaker_id": item.get("spk", ""),
                    "start_ms": item.get("start", ""),
                    "end_ms": item.get("end", ""),
                    "start": _ms_to_timestamp(item.get("start")),
                    "end": _ms_to_timestamp(item.get("end")),
                    "text": text,
                }
            )
    return sentences


def _format_speaker_transcript(sentences: list[dict[str, object]]) -> str:
    lines: list[str] = []
    for item in sentences:
        speaker = str(item.get("speaker") or "Speaker ?")
        start = str(item.get("start") or "")
        end = str(item.get("end") or "")
        time_range = f"[{start}-{end}] " if start or end else ""
        lines.append(f"{time_range}{speaker}: {item.get('text', '')}".strip())
    return "\n".join(line for line in lines if line).strip()


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
    speaker_diarization: bool,
    require_speaker_diarization: bool,
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

    spk_cache_status = _model_cache_status("cam++")
    if speaker_diarization and not spk_cache_status.get("complete"):
        print(
            "SenseVoice 说话人分离模型 cam++ 本地缓存不完整，"
            f"缺少 {spk_cache_status.get('missing')}；将尝试远程模型名，失败则降级纯转录。",
            file=sys.stderr,
        )

    base_model_kwargs: dict[str, object] = {
        "model": _resolve_model_ref(model_name),
        "trust_remote_code": True,
        "vad_model": _resolve_model_ref("fsmn-vad"),
        "vad_kwargs": {"max_single_segment_time": 30000},
        "punc_model": _resolve_model_ref("ct-punc"),
        "device": _select_device("auto"),
        "disable_update": True,
    }
    diarization_enabled = False
    try:
        model_kwargs = dict(base_model_kwargs)
        if speaker_diarization:
            model_kwargs.update({"spk_model": _resolve_model_ref("cam++")})
        model = AutoModel(**model_kwargs)
        diarization_enabled = speaker_diarization
    except (RuntimeError, TypeError, ValueError) as exc:
        if require_speaker_diarization:
            raise
        if speaker_diarization:
            print(
                f"SenseVoice 说话人分离不可用，降级为纯转录: {exc}",
                file=sys.stderr,
            )
        try:
            model = AutoModel(**base_model_kwargs)
        except RuntimeError as fallback_exc:
            if model_name == DEFAULT_SENSEVOICE_MODEL and "not registered" in str(fallback_exc):
                fallback_kwargs = dict(base_model_kwargs)
                fallback_kwargs["model"] = "SenseVoiceSmall"
                model = AutoModel(**fallback_kwargs)
            else:
                raise

    generate_kwargs: dict[str, object] = {
        "input": str(input_file),
        "language": language,
        "use_itn": True,
        "batch_size_s": 60,
        "merge_vad": True,
        "merge_length_s": 15,
        "sentence_timestamp": True,
    }
    try:
        result = model.generate(**generate_kwargs)
    except Exception as exc:
        if require_speaker_diarization or not speaker_diarization:
            raise
        print(
            f"SenseVoice 说话人分离生成失败，降级为纯转录: {exc}",
            file=sys.stderr,
        )
        model = AutoModel(**base_model_kwargs)
        diarization_enabled = False
        result = model.generate(**generate_kwargs)

    speaker_sentences = _extract_sentence_info(result)
    output_text = _format_speaker_transcript(speaker_sentences) or _extract_funasr_text(result)
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
            "model_cache": _model_cache_report(),
            "speaker_diarization_requested": speaker_diarization,
            "speaker_diarization_enabled": diarization_enabled,
            "speaker_diarization_detected": bool(speaker_sentences),
            "speakers": sorted({str(item.get("speaker")) for item in speaker_sentences if item.get("speaker")}),
            "sentence_info": speaker_sentences,
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
        "model": _resolve_model_ref(model_name),
        "trust_remote_code": True,
        "device": resolved_device,
        "hub": hub,
        "disable_update": True,
    }
    if use_vad:
        model_kwargs.update(
            {
                "vad_model": _resolve_model_ref("fsmn-vad"),
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
    parser.add_argument("input_file", nargs="?", help="音频文件路径")
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
        "--no-speaker-diarization",
        action="store_true",
        help="SenseVoice 不启用说话人分离（默认会尝试 cam++）",
    )
    parser.add_argument(
        "--require-speaker-diarization",
        action="store_true",
        help="如果 SenseVoice 说话人分离不可用则直接失败，而不是降级纯转录",
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
    parser.add_argument(
        "--check-model-cache",
        action="store_true",
        help="只检查本地 ASR 模型缓存完整性，不执行转录",
    )
    args = parser.parse_args()

    _configure_model_cache(args.cache_dir)
    if args.check_model_cache:
        _print_model_cache_report()
        report = _model_cache_report()
        models = report.get("models", {})
        if isinstance(models, dict) and all(
            isinstance(item, dict) and item.get("complete")
            for item in models.values()
        ):
            return 0
        return 1

    if not args.input_file:
        print("输入文件不存在: 请提供音频文件路径，或使用 --check-model-cache 仅检查模型缓存。", file=sys.stderr)
        return 1

    input_file = Path(args.input_file).expanduser().resolve()
    if not input_file.exists():
        print(f"输入文件不存在: {input_file}", file=sys.stderr)
        return 1

    output_dir = Path(args.output_dir).expanduser().resolve()
    output_dir.mkdir(parents=True, exist_ok=True)

    if args.engine in {"auto", "sensevoice"}:
        sensevoice_code = _run_sensevoice(
            input_file=input_file,
            output_dir=output_dir,
            model_name=args.model,
            language=args.language,
            output_format=args.output_format,
            speaker_diarization=not args.no_speaker_diarization,
            require_speaker_diarization=args.require_speaker_diarization,
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
