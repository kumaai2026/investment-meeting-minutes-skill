#!/usr/bin/env python3
"""High-quality local transcription wrapper for SenseVoice."""

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
DEFAULT_LOCAL_CACHE = Path("/Users/nananaranja/Documents/Codex/asr-model-cache")
MODEL_ALIASES = {
    "iic/SenseVoiceSmall": ("modelscope", "models/iic/SenseVoiceSmall"),
    "SenseVoiceSmall": ("modelscope", "models/iic/SenseVoiceSmall"),
}
REQUIRED_MODEL_FILES = {
    "iic/SenseVoiceSmall": ("config.yaml", "model.pt"),
    "SenseVoiceSmall": ("config.yaml", "model.pt"),
}
SENSEVOICE_TEXT_FORMATS = {"txt", "json", "all"}


def _configure_model_cache(cache_dir: str) -> None:
    cache_value = (
        cache_dir
        or os.environ.get("SENSEVOICE_MODEL_CACHE")
        or os.environ.get("FUNASR_MODEL_CACHE")
        or str(DEFAULT_LOCAL_CACHE)
    ).strip()
    root = Path(cache_value).expanduser().resolve()
    os.environ.setdefault("SENSEVOICE_MODEL_CACHE", str(root))
    os.environ.setdefault("FUNASR_MODEL_CACHE", str(root))
    os.environ.setdefault("MODELSCOPE_CACHE", str(root / "modelscope"))
    os.environ.setdefault("HF_HOME", str(root / "huggingface"))


def _model_cache_root() -> Path | None:
    candidates = [
        os.environ.get("SENSEVOICE_MODEL_CACHE"),
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


def _resolve_model_ref(model_name: str, *, allow_remote_model_lookup: bool = False) -> str:
    path = Path(model_name).expanduser()
    if path.exists() and _is_complete_model_dir(path, model_name):
        return str(path.resolve())
    for candidate in _model_candidates(model_name):
        if _is_complete_model_dir(candidate, model_name):
            return str(candidate)
    if not allow_remote_model_lookup:
        status = _model_cache_status(model_name)
        checked = ", ".join(str(item) for item in status.get("checked_paths", []) or [])
        missing = ", ".join(str(item) for item in status.get("missing", []) or [])
        detail = f"；检查路径: {checked}" if checked else ""
        missing_detail = f"；缺少: {missing}" if missing else ""
        raise FileNotFoundError(
            f"本地模型缓存不完整，已阻止远程模型查找: {model_name}{missing_detail}{detail}"
        )
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
        "models": {"sensevoice": _model_cache_status(DEFAULT_SENSEVOICE_MODEL)},
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


def _ensure_ffmpeg_for_current_process() -> None:
    env = _ensure_ffmpeg_in_path(dict(os.environ))
    if env.get("PATH") != os.environ.get("PATH"):
        os.environ["PATH"] = env["PATH"]


def _clean_sensevoice_text(text: str) -> str:
    """Remove SenseVoice control tags while preserving the spoken content."""
    text = re.sub(r"<\|[^|]+?\|>", "", text)
    return re.sub(r"\s+", " ", text).strip()


def _extract_model_text(result: object) -> str:
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


def _timestamp_pair_ms(value: object) -> tuple[object, object] | None:
    if isinstance(value, dict):
        start = value.get("start", value.get("start_ms", value.get("begin")))
        end = value.get("end", value.get("end_ms", value.get("finish")))
        if start is not None and end is not None:
            return start, end
    if isinstance(value, (list, tuple)) and len(value) >= 2:
        return value[0], value[1]
    return None


def _split_sentence_spans(text: str) -> list[tuple[int, int, str]]:
    spans: list[tuple[int, int, str]] = []
    start = 0
    for match in re.finditer(r"[^。！？!?；;\n]+[。！？!?；;]?", text):
        sentence = match.group(0).strip()
        if not sentence:
            continue
        spans.append((match.start(), match.end(), sentence))
        start = match.end()
    tail = text[start:].strip()
    if tail:
        spans.append((start, len(text), tail))
    return spans or [(0, len(text), text)] if text else []


def _segment_from_time_range(
    *,
    text: str,
    start_ms: object,
    end_ms: object,
    speaker: object = "",
    source: str,
) -> dict[str, object]:
    return {
        "speaker": _speaker_label(speaker) if str(speaker or "").strip() else "",
        "speaker_id": speaker if str(speaker or "").strip() else "",
        "start_ms": start_ms,
        "end_ms": end_ms,
        "start": _ms_to_timestamp(start_ms),
        "end": _ms_to_timestamp(end_ms),
        "text": text,
        "source": source,
    }


def _extract_sentence_info(result: object) -> list[dict[str, object]]:
    chunks = result if isinstance(result, list) else [result]
    sentences: list[dict[str, object]] = []
    for chunk in chunks:
        if not isinstance(chunk, dict):
            continue
        chunk_sentences: list[dict[str, object]] = []
        for item in chunk.get("sentence_info") or []:
            if not isinstance(item, dict):
                continue
            text = _clean_sensevoice_text(str(item.get("text") or item.get("sentence") or ""))
            if not text:
                continue
            chunk_sentences.append(
                _segment_from_time_range(
                    text=text,
                    start_ms=item.get("start", ""),
                    end_ms=item.get("end", ""),
                    speaker=item.get("spk", ""),
                    source="sentence_info",
                )
            )
        if chunk_sentences:
            sentences.extend(chunk_sentences)
            continue

        text = _clean_sensevoice_text(str(chunk.get("text") or ""))
        timestamp = chunk.get("timestamp")
        timestamp_pairs = [
            pair
            for pair in (_timestamp_pair_ms(item) for item in timestamp or [])
            if pair is not None
        ]
        if text and timestamp_pairs:
            spans = _split_sentence_spans(text)
            if len(timestamp_pairs) >= max(len(text), spans[-1][1] if spans else 0):
                for start_idx, end_idx, sentence in spans:
                    start_ms, _ = timestamp_pairs[max(start_idx, 0)]
                    _, end_ms = timestamp_pairs[min(max(end_idx - 1, 0), len(timestamp_pairs) - 1)]
                    sentences.append(
                        _segment_from_time_range(
                            text=sentence,
                            start_ms=start_ms,
                            end_ms=end_ms,
                            source="timestamp",
                        )
                    )
            else:
                start_ms, _ = timestamp_pairs[0]
                _, end_ms = timestamp_pairs[-1]
                sentences.append(
                    _segment_from_time_range(
                        text=text,
                        start_ms=start_ms,
                        end_ms=end_ms,
                        source="timestamp",
                    )
                )
            continue

        if text and chunk.get("start_ms") is not None and chunk.get("end_ms") is not None:
            sentences.append(
                _segment_from_time_range(
                    text=text,
                    start_ms=chunk.get("start_ms", ""),
                    end_ms=chunk.get("end_ms", ""),
                    source="chunk",
                )
            )
    return sentences


def _format_speaker_transcript(sentences: list[dict[str, object]]) -> str:
    lines: list[str] = []
    for item in sentences:
        speaker = str(item.get("speaker") or "").strip()
        start = str(item.get("start") or "")
        end = str(item.get("end") or "")
        time_range = f"[{start}-{end}] " if start or end else ""
        prefix = f"{speaker}: " if speaker else ""
        lines.append(f"{time_range}{prefix}{item.get('text', '')}".strip())
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
    allow_remote_model_lookup: bool,
    include_raw_json: bool,
) -> int:
    if output_format not in SENSEVOICE_TEXT_FORMATS:
        print(
            "SenseVoice 当前只允许输出 txt/json/all；禁止降级为 Whisper 生成字幕格式。",
            file=sys.stderr,
        )
        return 2

    _ensure_ffmpeg_for_current_process()

    try:
        from funasr import AutoModel  # type: ignore
    except Exception as exc:
        print(f"缺少 SenseVoice 运行依赖: {exc}", file=sys.stderr)
        return 127

    base_model_kwargs: dict[str, object] = {
        "model": _resolve_model_ref(model_name, allow_remote_model_lookup=allow_remote_model_lookup),
        "trust_remote_code": True,
        "device": _select_device("auto"),
        "disable_update": True,
    }
    try:
        model = AutoModel(**base_model_kwargs)
    except (RuntimeError, TypeError, ValueError) as exc:
        if model_name == DEFAULT_SENSEVOICE_MODEL and "not registered" in str(exc):
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
        "sentence_timestamp": True,
    }
    result = model.generate(**generate_kwargs)

    speaker_sentences = _extract_sentence_info(result)
    output_text = _format_speaker_transcript(speaker_sentences) or _extract_model_text(result)
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
            "timestamp_detected": bool(speaker_sentences),
            "speakers": sorted({str(item.get("speaker")) for item in speaker_sentences if item.get("speaker")}),
            "sentence_info": speaker_sentences,
        }
        if include_raw_json:
            payload["raw"] = result
        (output_dir / f"{stem}.json").write_text(
            json.dumps(payload, ensure_ascii=False, indent=2, default=str),
            encoding="utf-8",
        )

    print(f"SenseVoice 转录完成: {output_dir / f'{stem}.txt'}")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="使用本地 SenseVoice 转录音频；禁止降级为 Whisper")
    parser.add_argument("input_file", nargs="?", help="音频文件路径")
    parser.add_argument(
        "--output-dir",
        default=".",
        help="转录文件输出目录，默认当前目录",
    )
    parser.add_argument(
        "--engine",
        default="auto",
        choices=["auto", "sensevoice"],
        help="兼容旧调用的 ASR 引擎参数；当前只运行 SenseVoice",
    )
    parser.add_argument(
        "--model",
        default=DEFAULT_SENSEVOICE_MODEL,
        help="SenseVoice 模型名，默认 iic/SenseVoiceSmall",
    )
    parser.add_argument(
        "--cache-dir",
        default="",
        help="可选模型缓存根目录；也可用 SENSEVOICE_MODEL_CACHE 环境变量设置",
    )
    parser.add_argument(
        "--output-format",
        default="txt",
        choices=["txt", "json", "all"],
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
    parser.add_argument(
        "--allow-remote-model-lookup",
        action="store_true",
        help="允许在本地缓存缺失时使用远程模型名；默认关闭，避免每次整理会议纪要时重新下载模型",
    )
    parser.add_argument(
        "--debug-raw-json",
        action="store_true",
        help="调试时在 JSON 中额外保留模型原始返回；默认关闭以减少写盘体积",
    )
    args = parser.parse_args()

    _configure_model_cache(args.cache_dir)
    if args.check_model_cache:
        _print_model_cache_report()
        report = _model_cache_report()
        models = report.get("models", {})
        sensevoice = models.get("sensevoice") if isinstance(models, dict) else {}
        if isinstance(sensevoice, dict) and sensevoice.get("complete"):
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
        return _run_sensevoice(
            input_file=input_file,
            output_dir=output_dir,
            model_name=args.model,
            language=args.language,
            output_format=args.output_format,
            allow_remote_model_lookup=args.allow_remote_model_lookup,
            include_raw_json=args.debug_raw_json,
        )

    print("未知 ASR 引擎；只能使用 SenseVoice。", file=sys.stderr)
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
