#!/usr/bin/env python3
"""One-command health check for the local investment meeting workflow."""

from __future__ import annotations

import argparse
import glob
import hashlib
import importlib.util
import json
import math
import os
import re
import shutil
import sqlite3
import struct
import subprocess
import sys
import tempfile
import wave
from datetime import datetime
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

SCRIPT_DIR = Path(__file__).resolve().parent
VAULT_DIR = Path("/Users/kumaai/Documents/Codex/workspace/投资纪要工作流")
RAW_DIR = VAULT_DIR / "00 Inbox/会议原始记录"
MINUTES_DIR = VAULT_DIR / "01 Projects/会议纪要"
WECHAT_REPO_DIR = Path("/Users/kumaai/新会议纪要工作流")
WECHAT_ARTICLE_RAW_DIR = VAULT_DIR / "00 Inbox/微信公众号文章"
WECHAT_ARTICLE_DIR = VAULT_DIR / "01 Projects/微信公众号文章归档"
WECHAT_CHAT_RAW_DIR = VAULT_DIR / "00 Inbox/微信聊天记录"
WECHAT_CHAT_DIR = VAULT_DIR / "01 Projects/微信聊天分析"
NORTHSTAR_PATH = VAULT_DIR / "03 Resources/会议纪要整理工作流-北极星文档.md"
DIFY_DOC_PATH = VAULT_DIR / "03 Resources/Dify投资会议纪要工作流项目文档.md"
MAPPING_PATH = Path(
    "/Users/kumaai/Library/Application Support/kumaai-sync/meeting-minutes-review/dify_dataset_documents.json"
)
REVIEW_DRAFTS_DIR = Path(
    "/Users/kumaai/Library/Application Support/kumaai-sync/meeting-minutes-review/drafts"
)
ACCESS_CONFIG_PATH = Path(
    "/Users/kumaai/Library/Application Support/kumaai-sync/meeting-minutes-review/access-control.json"
)
ACCESS_DB_PATH = Path(
    "/Users/kumaai/Library/Application Support/kumaai-sync/meeting-minutes-review/access-users.sqlite3"
)
ADMIN_TOKEN_PATH = Path(
    "/Users/kumaai/Library/Application Support/kumaai-sync/meeting-minutes-review/admin-access-token.txt"
)
RCLONE_LOG_PATH = Path("/Users/kumaai/Library/Logs/kumaai-sync/investment-workflow-rclone.log")
ACCESS_AUDIT_LOG_PATH = Path("/Users/kumaai/Library/Logs/kumaai-sync/meeting-minutes-access-audit.jsonl")
DIFY_DOCKER_DIR = Path("/Users/kumaai/dify/docker")
DIFY_DB_CONTAINER = "docker-db_postgres-1"
DIFY_WORKFLOW_APP_ID = "8b8b90b1-432c-414a-842a-7426c628ae39"
LIVE_SKILL_DIR = Path("/Users/kumaai/.codex/skills/投资会议纪要整理")
TYPE_SKILL_NAMES = [
    "投资会议纪要-多人复盘会",
    "投资会议纪要-上市公司交流",
    "投资会议纪要-专家交流",
    "投资会议纪要-其他",
]
WECHAT_LAUNCH_AGENT_PATH = Path("/Users/kumaai/Library/LaunchAgents/com.kumaai.wechat-tools-bridge.plist")
DEFAULT_ASR_RUNTIME_PYTHON = Path(
    os.environ.get(
        "FUNASR_NANO_PYTHON",
        "/Users/nananaranja/Documents/会议纪要整理/.transcribe-venv/bin/python",
    )
)

REQUIRED_DIFY_SERVICES = {
    "nginx",
    "web",
    "api",
    "worker",
    "worker_beat",
    "plugin_daemon",
    "db_postgres",
    "redis",
    "weaviate",
    "sandbox",
    "ssrf_proxy",
}

STRICT_RUNTIME_MODULES = [
    ("Python 依赖: funasr", "funasr"),
    ("Python 依赖: modelscope", "modelscope"),
    ("Python 依赖: soundfile", "soundfile"),
    ("Python 依赖: librosa", "librosa"),
    ("Python 依赖: python-docx", "docx"),
]


def now_iso() -> str:
    return datetime.now().replace(microsecond=0).isoformat()


def check(status: str, name: str, message: str, **details: Any) -> dict[str, Any]:
    item: dict[str, Any] = {"status": status, "name": name, "message": message}
    if details:
        item["details"] = details
    return item


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def http_check(name: str, url: str, *, expect_json_ok: bool = False, required_text: str = "") -> dict[str, Any]:
    request = Request(url, headers={"User-Agent": "investment-workflow-health/1.0"})
    try:
        with urlopen(request, timeout=5) as response:
            status_code = response.status
            body_bytes = response.read(128 * 1024)
            content_type = response.headers.get("Content-Type", "")
    except HTTPError as exc:
        return check("error", name, f"HTTP {exc.code}", url=url)
    except (TimeoutError, URLError, OSError) as exc:
        return check("error", name, f"无法访问: {exc}", url=url)

    body = body_bytes.decode("utf-8", errors="replace")
    if status_code >= 400:
        return check("error", name, f"HTTP {status_code}", url=url)
    if expect_json_ok:
        try:
            payload = json.loads(body)
        except json.JSONDecodeError as exc:
            return check("error", name, f"返回不是 JSON: {exc}", url=url, content_type=content_type)
        if payload.get("ok") is not True:
            return check("error", name, "健康接口返回 ok=false", url=url, payload=payload)
        return check("ok", name, "在线", url=url, payload=payload)
    if required_text and required_text not in body:
        return check("warning", name, "可访问，但页面内容未命中预期文本", url=url, status_code=status_code)
    return check("ok", name, "可访问", url=url, status_code=status_code)


def path_check(name: str, path: Path, *, writable: bool = False) -> dict[str, Any]:
    if not path.exists():
        return check("error", name, "路径不存在", path=str(path))
    if writable and not os.access(path, os.W_OK):
        return check("error", name, "路径不可写", path=str(path))
    if path.is_dir():
        return check("ok", name, "目录存在" + ("且可写" if writable else ""), path=str(path))
    return check("ok", name, "文件存在", path=str(path), size=path.stat().st_size)


def command_exists_check(name: str, command: str, fallback: Path | None = None) -> dict[str, Any]:
    resolved = shutil.which(command)
    if resolved:
        return check("ok", name, "命令可用", path=resolved)
    if fallback and fallback.exists():
        return check("ok", name, "命令可用", path=str(fallback))
    return check("warning", name, "命令未找到", command=command)


def asr_runtime_python() -> Path:
    if DEFAULT_ASR_RUNTIME_PYTHON.exists():
        return DEFAULT_ASR_RUNTIME_PYTHON
    return Path(sys.executable)


def python_module_check(name: str, module: str, *, strict: bool, python_executable: Path | None = None) -> dict[str, Any]:
    python_path = python_executable or Path(sys.executable)
    if python_path == Path(sys.executable) and importlib.util.find_spec(module):
        return check("ok", name, "模块可导入", module=module, python=str(python_path))
    probe = "import importlib.util, sys; sys.exit(0 if importlib.util.find_spec(sys.argv[1]) else 1)"
    returncode, stdout, stderr = run_command([str(python_path), "-c", probe, module], timeout=10)
    if returncode == 0:
        return check("ok", name, "模块可导入", module=module, python=str(python_path))
    status = "error" if strict else "warning"
    return check(
        status,
        name,
        "模块不可导入；运行期禁止临时安装依赖",
        module=module,
        python=str(python_path),
        stderr=stderr.strip(),
    )


def run_command(args: list[str], *, cwd: Path | None = None, timeout: int = 20) -> tuple[int, str, str]:
    env = os.environ.copy()
    env["PYTHONUTF8"] = "1"
    env["PYTHONIOENCODING"] = "utf-8"
    try:
        result = subprocess.run(args, cwd=cwd, text=True, capture_output=True, timeout=timeout, env=env)
    except FileNotFoundError as exc:
        return 127, "", str(exc)
    return result.returncode, result.stdout, result.stderr


def asr_model_cache_check(*, strict: bool) -> dict[str, Any]:
    script = SCRIPT_DIR / "transcribe_audio.py"
    if not script.exists():
        return check("error", "ASR 模型缓存", "转写脚本不存在", path=str(script))
    try:
        returncode, stdout, stderr = run_command([sys.executable, str(script), "--check-model-cache"], timeout=30)
    except subprocess.TimeoutExpired:
        status = "error" if strict else "warning"
        return check(status, "ASR 模型缓存", "模型缓存检查超时", path=str(script))
    try:
        payload = json.loads(stdout)
    except json.JSONDecodeError as exc:
        status = "error" if strict else "warning"
        return check(
            status,
            "ASR 模型缓存",
            f"模型缓存检查输出不是 JSON: {exc}",
            stdout=stdout[-2000:],
            stderr=stderr[-2000:],
        )

    models = payload.get("models") if isinstance(payload.get("models"), dict) else {}
    required_incomplete = {
        name: model
        for name, model in models.items()
        if name == "sensevoice" and isinstance(model, dict) and not model.get("complete")
    }
    optional_incomplete = {
        name: model
        for name, model in models.items()
        if name != "sensevoice" and isinstance(model, dict) and not model.get("complete")
    }
    if returncode == 0 and not required_incomplete:
        return check(
            "ok",
            "ASR 模型缓存",
            "纯 SenseVoice 必需模型缓存完整；Nano/VAD/说话人分离按辅助能力处理",
            cache_root=payload.get("cache_root"),
            models=models,
            optional_incomplete=optional_incomplete,
        )
    status = "error" if strict else "warning"
    return check(
        status,
        "ASR 模型缓存",
        "纯 SenseVoice 必需模型缓存不完整；运行期禁止远程查找或下载模型",
        cache_root=payload.get("cache_root"),
        incomplete=required_incomplete,
        optional_incomplete=optional_incomplete,
        stderr=stderr.strip(),
    )


def sensevoice_service_model_cache_check(*, strict: bool) -> dict[str, Any]:
    name = "SenseVoice 服务模型缓存"
    request = Request("http://127.0.0.1:8765/health", headers={"User-Agent": "investment-workflow-health/1.0"})
    try:
        with urlopen(request, timeout=5) as response:
            payload = json.loads(response.read(128 * 1024).decode("utf-8", errors="replace"))
    except Exception as exc:  # noqa: BLE001
        status = "error" if strict else "warning"
        return check(status, name, f"无法读取服务健康状态: {exc}", url="http://127.0.0.1:8765/health")

    model_cache = payload.get("model_cache") if isinstance(payload.get("model_cache"), dict) else {}
    models = model_cache.get("models") if isinstance(model_cache.get("models"), dict) else {}
    required_incomplete = {
        model_name: model
        for model_name, model in models.items()
        if model_name == "sensevoice" and isinstance(model, dict) and not model.get("complete")
    }
    optional_incomplete = {
        model_name: model
        for model_name, model in models.items()
        if model_name != "sensevoice" and isinstance(model, dict) and not model.get("complete")
    }
    if payload.get("ok") is True and models and not required_incomplete:
        return check(
            "ok",
            name,
            "服务使用的纯 SenseVoice 必需模型缓存完整；Nano/VAD/说话人分离按辅助能力处理",
            cache_root=model_cache.get("cache_root"),
            python=model_cache.get("python"),
            optional_incomplete=optional_incomplete,
        )
    status = "error" if strict else "warning"
    return check(
        status,
        name,
        "服务使用的纯 SenseVoice 必需模型缓存不完整；运行期禁止远程下载模型",
        cache_root=model_cache.get("cache_root"),
        python=model_cache.get("python"),
        incomplete=required_incomplete,
        optional_incomplete=optional_incomplete,
    )


def write_smoke_wav(path: Path, *, seconds: float = 0.6, sample_rate: int = 16000) -> None:
    frame_count = int(seconds * sample_rate)
    amplitude = 8000
    frequency = 440.0
    with wave.open(str(path), "wb") as handle:
        handle.setnchannels(1)
        handle.setsampwidth(2)
        handle.setframerate(sample_rate)
        frames = bytearray()
        for index in range(frame_count):
            sample = int(amplitude * math.sin(2 * math.pi * frequency * index / sample_rate))
            frames.extend(struct.pack("<h", sample))
        handle.writeframes(bytes(frames))


def sensevoice_service_smoke_check(*, strict: bool) -> dict[str, Any]:
    name = "SenseVoice 服务转写 smoke"
    boundary = "----investment-meeting-smoke-boundary"
    with tempfile.TemporaryDirectory(prefix="meeting-asr-smoke-") as tmp:
        audio_path = Path(tmp) / "smoke.wav"
        write_smoke_wav(audio_path)
        audio_bytes = audio_path.read_bytes()
        body = b"".join(
            [
                f"--{boundary}\r\n".encode("utf-8"),
                b'Content-Disposition: form-data; name="audio"; filename="smoke.wav"\r\n',
                b"Content-Type: audio/wav\r\n\r\n",
                audio_bytes,
                f"\r\n--{boundary}--\r\n".encode("utf-8"),
            ]
        )
    request = Request(
        "http://127.0.0.1:8765/transcribe",
        data=body,
        headers={
            "Content-Type": f"multipart/form-data; boundary={boundary}",
            "User-Agent": "investment-workflow-health/1.0",
        },
        method="POST",
    )
    try:
        with urlopen(request, timeout=120) as response:
            payload = json.loads(response.read(256 * 1024).decode("utf-8", errors="replace"))
    except HTTPError as exc:
        try:
            payload = json.loads(exc.read(256 * 1024).decode("utf-8", errors="replace"))
        except Exception:
            payload = {"error": str(exc)}
        status = "error" if strict else "warning"
        return check(status, name, f"HTTP {exc.code}", url="http://127.0.0.1:8765/transcribe", payload=payload)
    except Exception as exc:  # noqa: BLE001
        status = "error" if strict else "warning"
        return check(status, name, f"转写 smoke 失败: {exc}", url="http://127.0.0.1:8765/transcribe")

    if payload.get("ok") is True:
        return check(
            "ok",
            name,
            "服务完成真实转写调用",
            engine=payload.get("engine"),
            model=payload.get("model"),
            timestamp_detected=payload.get("timestamp_detected"),
            text_preview=str(payload.get("text") or "")[:80],
        )
    status = "error" if strict else "warning"
    return check(status, name, "服务返回 ok=false", payload=payload)


def strict_runtime_checks(strict: bool, *, runtime_smoke: bool = False) -> list[dict[str, Any]]:
    runtime_python = asr_runtime_python()
    checks = [
        python_module_check(name, module, strict=strict, python_executable=runtime_python)
        for name, module in STRICT_RUNTIME_MODULES
    ]
    checks.append(asr_model_cache_check(strict=strict))
    checks.append(sensevoice_service_model_cache_check(strict=strict))
    if runtime_smoke:
        checks.append(sensevoice_service_smoke_check(strict=strict))
    return checks


def docker_check() -> dict[str, Any]:
    if not shutil.which("docker"):
        return check("error", "Docker", "docker 命令不可用")
    try:
        returncode, stdout, stderr = run_command(["docker", "ps", "--format", "{{json .}}"], timeout=20)
    except subprocess.TimeoutExpired:
        return check("error", "Docker", "docker ps 超时")
    if returncode != 0:
        return check("error", "Docker", "docker ps 失败", stderr=stderr.strip())

    services: dict[str, dict[str, str]] = {}
    for line in stdout.splitlines():
        if not line.strip():
            continue
        try:
            row = json.loads(line)
        except json.JSONDecodeError:
            continue
        labels = str(row.get("Labels") or "")
        if f"com.docker.compose.project.working_dir={DIFY_DOCKER_DIR}" not in labels:
            continue
        match = re.search(r"com\.docker\.compose\.service=([^,]+)", labels)
        service = match.group(1) if match else str(row.get("Names") or "")
        services[service] = {
            "name": str(row.get("Names") or ""),
            "state": str(row.get("State") or ""),
            "status": str(row.get("Status") or ""),
            "ports": str(row.get("Ports") or ""),
        }

    missing = sorted(REQUIRED_DIFY_SERVICES - set(services))
    not_running = sorted(name for name, row in services.items() if row.get("state") != "running")
    status = "ok"
    message = "Dify 容器运行中"
    if missing or not_running:
        status = "error"
        message = "Dify 容器缺失或未运行"
    return check(
        status,
        "Dify Docker",
        message,
        services=services,
        missing=missing,
        not_running=not_running,
    )


def launch_agent_check(name: str, label: str, plist_path: Path) -> dict[str, Any]:
    if not plist_path.exists():
        return check("warning", name, "LaunchAgent plist 不存在", path=str(plist_path))
    try:
        returncode, stdout, stderr = run_command(["launchctl", "print", f"gui/{os.getuid()}/{label}"], timeout=10)
    except subprocess.TimeoutExpired:
        return check("warning", name, "launchctl 检查超时", path=str(plist_path))
    if returncode != 0:
        return check("warning", name, "LaunchAgent 未加载", path=str(plist_path), stderr=stderr.strip())
    state_match = re.search(r"state = ([^\n]+)", stdout)
    pid_match = re.search(r"\bpid = (\d+)", stdout)
    state = state_match.group(1).strip() if state_match else ""
    status = "ok" if state == "running" else "warning"
    return check(status, name, f"LaunchAgent {state or '状态未知'}", path=str(plist_path), pid=pid_match.group(1) if pid_match else "")


def rclone_log_check() -> dict[str, Any]:
    if not RCLONE_LOG_PATH.exists():
        return check("warning", "Google Drive 同步日志", "尚未找到同步日志", path=str(RCLONE_LOG_PATH))
    try:
        lines = RCLONE_LOG_PATH.read_text(encoding="utf-8", errors="replace").splitlines()
    except OSError as exc:
        return check("warning", "Google Drive 同步日志", f"无法读取日志: {exc}", path=str(RCLONE_LOG_PATH))

    tail = lines[-80:]
    exit_lines = [line for line in tail if "sync exit code:" in line]
    last_exit = exit_lines[-1] if exit_lines else ""
    if "sync exit code: 0" in last_exit:
        return check("ok", "Google Drive 最近同步", "最近一次同步退出码为 0", log=str(RCLONE_LOG_PATH), last_exit=last_exit)
    if last_exit:
        return check("warning", "Google Drive 最近同步", "最近一次同步可能失败", log=str(RCLONE_LOG_PATH), last_exit=last_exit)
    return check("warning", "Google Drive 最近同步", "日志中没有最近退出码", log=str(RCLONE_LOG_PATH))


def mapping_audit_check() -> dict[str, Any]:
    script = SCRIPT_DIR / "audit_dify_dataset_mapping.py"
    if not script.exists():
        return check("error", "知识库映射审计", "审计脚本不存在", path=str(script))
    try:
        returncode, stdout, stderr = run_command([sys.executable, str(script), "--json"], timeout=30)
    except subprocess.TimeoutExpired:
        return check("error", "知识库映射审计", "审计超时")
    if returncode not in (0, 1):
        return check("error", "知识库映射审计", "审计脚本失败", stderr=stderr.strip(), stdout=stdout[-2000:])
    try:
        payload = json.loads(stdout)
    except json.JSONDecodeError as exc:
        return check("error", "知识库映射审计", f"审计输出不是 JSON: {exc}", stdout=stdout[-2000:])

    issue_count = int(payload.get("issue_count") or 0)
    error_count = sum(1 for issue in payload.get("issues", []) if issue.get("severity") == "error")
    warning_count = sum(1 for issue in payload.get("issues", []) if issue.get("severity") == "warning")
    if error_count:
        status = "error"
        message = f"发现 {error_count} 个错误、{warning_count} 个警告"
    elif warning_count:
        status = "warning"
        message = f"发现 {warning_count} 个警告，正式流程仍可运行"
    else:
        status = "ok"
        message = "映射无异常"
    return check(
        status,
        "知识库映射审计",
        message,
        mapping_count=payload.get("mapping_count"),
        minutes_count=payload.get("minutes_count"),
        issue_count=issue_count,
        warning_count=warning_count,
        error_count=error_count,
    )


def external_knowledge_config_check() -> dict[str, Any]:
    script = Path("/Users/kumaai/新会议纪要工作流/scripts/check_dify_knowledge_tools_config.py")
    if not script.exists():
        return check("warning", "外部资料知识库同步配置", "配置检查脚本不存在", path=str(script))
    try:
        returncode, stdout, stderr = run_command([sys.executable, str(script), "--json"], timeout=20)
    except subprocess.TimeoutExpired:
        return check("warning", "外部资料知识库同步配置", "配置检查超时")
    if returncode not in (0, 1):
        return check("warning", "外部资料知识库同步配置", "配置检查脚本失败", stderr=stderr.strip(), stdout=stdout[-2000:])
    try:
        payload = json.loads(stdout)
    except json.JSONDecodeError as exc:
        return check("warning", "外部资料知识库同步配置", f"配置检查输出不是 JSON: {exc}", stdout=stdout[-2000:])
    if payload.get("ok") is True:
        return check("ok", "外部资料知识库同步配置", "已配置", config_path=payload.get("config_path"), mapping_path=payload.get("mapping_path"))
    return check(
        "warning",
        "外部资料知识库同步配置",
        "未完成；本地归档可用，知识库同步会跳过",
        config_path=payload.get("config_path"),
        checks=payload.get("checks"),
    )


def access_control_check() -> dict[str, Any]:
    if not ACCESS_DB_PATH.exists():
        return check("warning", "公网访问权限配置", "本机用户数据库尚未创建", path=str(ACCESS_DB_PATH), legacy_config_path=str(ACCESS_CONFIG_PATH))
    try:
        conn = sqlite3.connect(ACCESS_DB_PATH)
        conn.row_factory = sqlite3.Row
        rows = conn.execute("SELECT user_id, role, disabled FROM access_users").fetchall()
        conn.close()
    except Exception as exc:
        return check("warning", "公网访问权限配置", f"用户数据库无法读取: {exc}", path=str(ACCESS_DB_PATH))
    users = [dict(row) for row in rows]
    admin_users = [item for item in users if str(item.get("role") or "").lower() == "admin" and not item.get("disabled")]
    if not users or not admin_users:
        return check("warning", "公网访问权限配置", "用户数据库存在但缺少启用的管理员用户", path=str(ACCESS_DB_PATH))
    mode = oct(ACCESS_DB_PATH.stat().st_mode & 0o777)
    token_mode = oct(ADMIN_TOKEN_PATH.stat().st_mode & 0o777) if ADMIN_TOKEN_PATH.exists() else ""
    return check(
        "ok",
        "公网访问权限配置",
        "已配置本机 SQLite 用户数据库和管理员用户",
        path=str(ACCESS_DB_PATH),
        legacy_config_path=str(ACCESS_CONFIG_PATH) if ACCESS_CONFIG_PATH.exists() else "",
        user_count=len(users),
        admin_count=len(admin_users),
        mode=mode,
        admin_token_path=str(ADMIN_TOKEN_PATH) if ADMIN_TOKEN_PATH.exists() else "",
        admin_token_mode=token_mode,
    )


def access_audit_log_check() -> dict[str, Any]:
    if ACCESS_AUDIT_LOG_PATH.exists():
        try:
            last_lines = ACCESS_AUDIT_LOG_PATH.read_text(encoding="utf-8", errors="replace").splitlines()[-20:]
            event_count = len(last_lines)
        except Exception:
            event_count = 0
        return check(
            "ok",
            "公网访问审计日志",
            "审计日志可写入",
            path=str(ACCESS_AUDIT_LOG_PATH),
            size=ACCESS_AUDIT_LOG_PATH.stat().st_size,
            recent_event_count=event_count,
        )
    if os.access(ACCESS_AUDIT_LOG_PATH.parent, os.W_OK):
        return check("warning", "公网访问审计日志", "审计日志尚未生成，但目录可写", path=str(ACCESS_AUDIT_LOG_PATH))
    return check("warning", "公网访问审计日志", "审计日志目录不可写", path=str(ACCESS_AUDIT_LOG_PATH))


def public_access_check() -> dict[str, Any]:
    script = SCRIPT_DIR / "check_public_access.py"
    check_name = "公网入口 kuma.d91.global"
    if not script.exists():
        return check("warning", check_name, "公网检查脚本不存在", path=str(script))
    try:
        returncode, stdout, stderr = run_command([sys.executable, str(script), "--json"], timeout=20)
    except subprocess.TimeoutExpired:
        return check("warning", check_name, "公网检查超时")
    if returncode not in (0, 1):
        return check("warning", check_name, "公网检查脚本失败", stderr=stderr.strip(), stdout=stdout[-2000:])
    try:
        payload = json.loads(stdout)
    except json.JSONDecodeError as exc:
        return check("warning", check_name, f"公网检查输出不是 JSON: {exc}", stdout=stdout[-2000:])
    status = "ok" if payload.get("ok") is True else "warning"
    check_name = f"公网入口 {payload.get('domain') or 'kuma.d91.global'}"
    return check(
        status,
        check_name,
        str(payload.get("message") or ""),
        dns_records=payload.get("dns_records"),
        local_http_host_header_ok=payload.get("local_http_host_header_ok"),
        forced_local_https_ok=payload.get("forced_local_https_ok"),
        public_https_ok=payload.get("public_https_ok"),
        protected_paths_ok=payload.get("protected_paths_ok"),
        protected_path_checks=payload.get("protected_path_checks"),
        public_https_error=payload.get("public_https_error"),
    )


def dify_workflow_output_contract_check() -> dict[str, Any]:
    query = (
        "select graph from workflows "
        f"where app_id='{DIFY_WORKFLOW_APP_ID}' and type='workflow' "
        "order by created_at desc limit 1;"
    )
    try:
        returncode, stdout, stderr = run_command(
            ["docker", "exec", DIFY_DB_CONTAINER, "psql", "-U", "postgres", "-d", "dify", "-t", "-A", "-c", query],
            timeout=20,
        )
    except subprocess.TimeoutExpired:
        return check("warning", "Dify 工作流输出契约", "读取 workflow 图超时", app_id=DIFY_WORKFLOW_APP_ID)
    if returncode != 0:
        return check("warning", "Dify 工作流输出契约", "无法读取 workflow 图", stderr=stderr.strip())
    graph_text = stdout.strip()
    if not graph_text:
        return check("warning", "Dify 工作流输出契约", "未找到目标 workflow 图", app_id=DIFY_WORKFLOW_APP_ID)
    try:
        graph = json.loads(graph_text)
    except json.JSONDecodeError as exc:
        return check("warning", "Dify 工作流输出契约", f"workflow graph 不是 JSON: {exc}")

    end_nodes = [
        node for node in graph.get("nodes", [])
        if (node.get("data") or {}).get("type") == "end"
    ]
    if not end_nodes:
        return check("warning", "Dify 工作流输出契约", "未找到 End 节点", app_id=DIFY_WORKFLOW_APP_ID)

    outputs: dict[str, list[str]] = {}
    for node in end_nodes:
        data = node.get("data") or {}
        for item in data.get("outputs") or []:
            if not isinstance(item, dict):
                continue
            variable = str(item.get("variable") or "").strip()
            selector = item.get("value_selector") or []
            outputs[variable] = [str(part) for part in selector]

    required = {
        "result_markdown": ["1779700000001", "result_markdown"],
        "review_url": ["1779400000001", "review_url"],
        "drafts_url": ["1779400000001", "drafts_url"],
        "history_url": ["1779400000001", "history_url"],
        "draft_id": ["1779400000001", "draft_id"],
    }
    missing = [name for name in required if name not in outputs]
    wrong_selector = {
        name: outputs.get(name)
        for name, selector in required.items()
        if name in outputs and outputs.get(name) != selector
    }
    if missing or wrong_selector:
        return check(
            "warning",
            "Dify 工作流输出契约",
            "结构化输出字段缺失或来源不一致",
            app_id=DIFY_WORKFLOW_APP_ID,
            missing=missing,
            wrong_selector=wrong_selector,
            outputs=sorted(outputs),
        )
    return check(
        "ok",
        "Dify 工作流输出契约",
        "End 节点已输出 result_markdown/review_url/drafts_url/history_url/draft_id",
        app_id=DIFY_WORKFLOW_APP_ID,
        outputs=sorted(outputs),
    )


def skill_sync_checks() -> list[dict[str, Any]]:
    checks: list[dict[str, Any]] = []
    skill_names = ["投资会议纪要整理", *TYPE_SKILL_NAMES]
    plugin_roots = sorted(
        Path(path)
        for path in glob.glob("/Users/kumaai/dify/docker/volumes/plugin_daemon/cwd/*/skill_agent-*/skills")
    )
    archive_root = VAULT_DIR / "04 Archive/Skills/investment-meeting-minutes-2026-05-12-d91-openminute"

    for skill_name in skill_names:
        live_dir = Path("/Users/kumaai/.codex/skills") / skill_name
        live_skill = live_dir / "SKILL.md"
        if not live_skill.exists():
            checks.append(check("error", f"Codex Skill: {skill_name}", "live SKILL.md 不存在", path=str(live_skill)))
            continue
        live_hash = sha256_file(live_skill)
        targets: list[tuple[str, Path]] = [
            (f"Skill 归档: {skill_name}", archive_root / skill_name / "SKILL.md"),
        ]
        for root in plugin_roots:
            targets.append((f"Dify Skill Agent: {skill_name}", root / skill_name / "SKILL.md"))
            if skill_name == "投资会议纪要整理":
                targets.append((f"Dify Skill Agent: investment-meeting-minutes", root / "investment-meeting-minutes" / "SKILL.md"))

        seen: set[Path] = set()
        for name, path in targets:
            if path in seen:
                continue
            seen.add(path)
            if not path.exists():
                checks.append(check("warning", name, "目标 SKILL.md 不存在", path=str(path)))
                continue
            if sha256_file(path) == live_hash:
                checks.append(check("ok", name, "与 Codex live skill 一致", path=str(path)))
            else:
                checks.append(check("warning", name, "与 Codex live skill 存在差异", path=str(path)))
    return checks


def collect_checks(include_public: bool, *, strict: bool = False, runtime_smoke: bool = False) -> list[dict[str, Any]]:
    checks: list[dict[str, Any]] = [
        path_check("Obsidian Vault", VAULT_DIR, writable=True),
        path_check("原始记录归档目录", RAW_DIR, writable=True),
        path_check("正式会议纪要目录", MINUTES_DIR, writable=True),
        path_check("微信资料工具目录", WECHAT_REPO_DIR),
        path_check("微信公众号原始归档目录", WECHAT_ARTICLE_RAW_DIR, writable=True),
        path_check("微信公众号 Markdown 归档目录", WECHAT_ARTICLE_DIR, writable=True),
        path_check("微信聊天原始归档目录", WECHAT_CHAT_RAW_DIR, writable=True),
        path_check("微信聊天分析目录", WECHAT_CHAT_DIR, writable=True),
        path_check("人工校对草稿目录", REVIEW_DRAFTS_DIR, writable=True),
        path_check("北极星文档", NORTHSTAR_PATH),
        path_check("Dify 项目文档", DIFY_DOC_PATH),
        path_check("知识库映射文件", MAPPING_PATH),
        command_exists_check("rclone", "rclone", Path("/Users/kumaai/.local/bin/rclone")),
        http_check("D91 前台首页", "http://127.0.0.1:1000/", required_text="D91 AI投研平台"),
        http_check("D91 工具页", "http://127.0.0.1:1000/tools", required_text="OpenMinute-会议纪要"),
        http_check("Kuma 会议纪要导入页", "http://127.0.0.1:1000/apps/meeting-minutes/import", required_text="导入会议材料"),
        http_check("Kuma 历史纪要页", "http://127.0.0.1:1000/history", required_text="历史会议纪要"),
        http_check("Kuma 待校对草稿页", "http://127.0.0.1:1000/drafts", required_text="待校对草稿"),
        http_check("Kuma 外部资料页", "http://127.0.0.1:1000/external-sources", required_text="外部资料归档"),
        http_check("Kuma 访问用户页", "http://127.0.0.1:1000/access-users", required_text="访问用户"),
        http_check(
            "Dify 工作流入口",
            "http://localhost:18081/explore/installed/4e99e8b0-7c35-4d38-a51f-5cbcc4ed1093",
        ),
        http_check("人工校对服务", "http://127.0.0.1:8767/health", expect_json_ok=True),
        http_check("Obsidian 导出桥", "http://127.0.0.1:8766/health", expect_json_ok=True),
        http_check("SenseVoice 转录服务", "http://127.0.0.1:8765/health", expect_json_ok=True),
        http_check("微信资料工具桥", "http://127.0.0.1:8770/health", expect_json_ok=True),
        launch_agent_check("微信资料工具 LaunchAgent", "com.kumaai.wechat-tools-bridge", WECHAT_LAUNCH_AGENT_PATH),
        docker_check(),
        dify_workflow_output_contract_check(),
        rclone_log_check(),
        mapping_audit_check(),
        external_knowledge_config_check(),
        access_control_check(),
        access_audit_log_check(),
    ]
    if strict:
        checks.extend(strict_runtime_checks(strict=True, runtime_smoke=runtime_smoke))
    checks.extend(skill_sync_checks())
    if include_public:
        checks.append(public_access_check())
    return checks


def summarize(checks: list[dict[str, Any]]) -> dict[str, Any]:
    counts = {"ok": 0, "warning": 0, "error": 0}
    for item in checks:
        status = str(item.get("status") or "warning")
        counts[status] = counts.get(status, 0) + 1
    if counts.get("error", 0):
        overall = "error"
    elif counts.get("warning", 0):
        overall = "warning"
    else:
        overall = "ok"
    return {"overall": overall, "counts": counts}


def print_text_report(report: dict[str, Any]) -> None:
    summary = report["summary"]
    print(f"整体状态: {summary['overall'].upper()}")
    print(f"生成时间: {report['generated_at']}")
    print(f"检查项: OK {summary['counts'].get('ok', 0)} / WARNING {summary['counts'].get('warning', 0)} / ERROR {summary['counts'].get('error', 0)}")
    print()
    for item in report["checks"]:
        label = str(item["status"]).upper()
        print(f"[{label}] {item['name']}: {item['message']}")
        details = item.get("details") or {}
        for key in ("path", "url", "log", "last_exit"):
            if details.get(key):
                print(f"  - {key}: {details[key]}")
        if item["name"] == "知识库映射审计":
            print(
                "  - mapping/minutes/issues: "
                f"{details.get('mapping_count')}/{details.get('minutes_count')}/{details.get('issue_count')}"
            )
        if item["name"] == "Dify Docker":
            missing = details.get("missing") or []
            if missing:
                print(f"  - missing: {', '.join(missing)}")


def main() -> int:
    parser = argparse.ArgumentParser(description="一键检查投资会议纪要工作流本机健康状态")
    parser.add_argument("--json", action="store_true", help="输出 JSON")
    parser.add_argument("--include-public", action="store_true", help="额外检查公网域名 kuma.d91.global")
    parser.add_argument("--strict", action="store_true", help="正式运行前严格检查本地依赖和 ASR 模型缓存；缺失即失败，不触发下载")
    parser.add_argument("--runtime-smoke", action="store_true", help="在 --strict 中额外调用 SenseVoice 服务执行真实短音频转写；耗时较长")
    args = parser.parse_args()

    checks = collect_checks(include_public=args.include_public, strict=args.strict, runtime_smoke=args.runtime_smoke)
    report = {
        "generated_at": now_iso(),
        "strict": bool(args.strict),
        "runtime_smoke": bool(args.runtime_smoke),
        "summary": summarize(checks),
        "checks": checks,
    }
    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2))
    else:
        print_text_report(report)
    return 1 if report["summary"]["overall"] == "error" else 0


if __name__ == "__main__":
    raise SystemExit(main())
