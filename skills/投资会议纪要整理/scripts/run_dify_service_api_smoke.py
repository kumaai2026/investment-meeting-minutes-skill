#!/usr/bin/env python3
"""Run a Dify Service API smoke test with a temporary app token."""

from __future__ import annotations

import argparse
import json
import os
import re
import secrets
import subprocess
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any

SCRIPT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPT_DIR))

from validate_meeting_minutes_contract import validate_contract  # noqa: E402

DIFY_BASE_URL = "http://localhost:18081"
REVIEW_BASE_URL = os.environ.get("MEETING_REVIEW_BASE_URL", "http://localhost:8767").rstrip("/")
DIFY_DB_CONTAINER = "docker-db_postgres-1"
DIFY_APP_ID = "8b8b90b1-432c-414a-842a-7426c628ae39"

SMOKE_INPUTS = {
    "transcript_text": (
        "主持人：请介绍半导体设备订单变化。\n"
        "张三：中芯国际相关设备订单能见度改善，但我现在没有加仓，后续还要看交付节奏。\n"
        "主持人：还有哪些不确定？\n"
        "张三：部分客户名称和具体订单金额需要继续确认。"
    ),
    "meeting_date": "2026-05-09",
    "meeting_title": "Dify Service API Smoke Test",
    "meeting_type": "专家交流",
    "custom_meeting_type": "",
    "meeting_series": "研究所周会",
    "custom_meeting_series": "",
    "review_date": "2026-05-09",
    "speakers": "主持人, 张三",
    "correction_notes": "小样本 smoke test；按当前两节结构整理，保留原文信息。",
    "input_reviewed": "true",
    "source_input_draft_id": "service-api-smoke-pre-reviewed",
}


def run_command(args: list[str], *, timeout: int = 30) -> tuple[int, str, str]:
    result = subprocess.run(args, text=True, capture_output=True, timeout=timeout)
    return result.returncode, result.stdout, result.stderr


def psql_scalar(sql: str, *, timeout: int = 30) -> str:
    returncode, stdout, stderr = run_command(
        ["docker", "exec", DIFY_DB_CONTAINER, "psql", "-U", "postgres", "-d", "dify", "-t", "-A", "-c", sql],
        timeout=timeout,
    )
    if returncode != 0:
        raise RuntimeError(stderr.strip() or stdout.strip() or "psql failed")
    return stdout.strip()


def create_temp_token() -> tuple[str, str]:
    tenant_id = psql_scalar(f"select tenant_id from apps where id='{DIFY_APP_ID}' limit 1;")
    if not tenant_id:
        raise RuntimeError(f"Dify app not found: {DIFY_APP_ID}")
    token = "app-" + secrets.token_urlsafe(48)
    stdout = psql_scalar(
        "insert into api_tokens (app_id, type, token, tenant_id) "
        f"values ('{DIFY_APP_ID}', 'app', '{token}', '{tenant_id}') returning id;"
    )
    match = re.search(r"[0-9a-fA-F-]{36}", stdout)
    if not match:
        raise RuntimeError("temporary token was not created")
    return match.group(0), token


def delete_temp_token(token_id: str) -> bool:
    if not token_id:
        return False
    psql_scalar(f"delete from api_tokens where id='{token_id}';")
    return True


def call_workflow(token: str, user: str, timeout: int) -> dict[str, Any]:
    payload = {
        "inputs": SMOKE_INPUTS,
        "response_mode": "blocking",
        "user": user,
    }
    request = urllib.request.Request(
        f"{DIFY_BASE_URL}/v1/workflows/run",
        data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
        headers={
            "Authorization": "Bearer " + token,
            "Content-Type": "application/json",
            "User-Agent": "investment-workflow-dify-smoke/1.0",
        },
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=timeout) as response:
        body = response.read().decode("utf-8")
    return json.loads(body)


def url_path(value: str) -> str:
    value = str(value or "").strip()
    if not value:
        return ""
    parsed = urllib.parse.urlparse(value)
    if parsed.scheme:
        return parsed.path + (("?" + parsed.query) if parsed.query else "")
    return value


def get_local_page(path: str) -> tuple[int, str]:
    request = urllib.request.Request(f"{REVIEW_BASE_URL}{path}", headers={"User-Agent": "investment-workflow-dify-smoke/1.0"})
    with urllib.request.urlopen(request, timeout=20) as response:
        return response.status, response.read().decode("utf-8", errors="replace")


def extract_note(result_markdown: str) -> str:
    marker = "# 投资会议纪要"
    index = result_markdown.find(marker)
    return result_markdown[index:].strip() if index >= 0 else result_markdown.strip()


def validate_response(response: dict[str, Any]) -> dict[str, Any]:
    data = response.get("data") or {}
    outputs = data.get("outputs") or {}
    result_markdown = str(outputs.get("result_markdown") or "")
    draft_id = str(outputs.get("draft_id") or "")
    review_url = url_path(str(outputs.get("review_url") or ""))
    drafts_url = url_path(str(outputs.get("drafts_url") or ""))
    history_url = url_path(str(outputs.get("history_url") or ""))
    note_markdown = extract_note(result_markdown)
    contract = validate_contract(note_markdown, required_terms=["中芯国际", "没有加仓", "交付节奏"])

    errors: list[str] = []
    if data.get("status") != "succeeded":
        errors.append(f"workflow status is {data.get('status')}")
    if not result_markdown:
        errors.append("missing result_markdown")
    if not review_url:
        errors.append("missing review_url")
    if not drafts_url:
        errors.append("missing drafts_url")
    if not history_url:
        errors.append("missing history_url")
    if not draft_id:
        errors.append("missing draft_id")
    if "**会议标题**" not in note_markdown:
        errors.append("missing meeting title metadata")
    if "**会议类型**" not in note_markdown:
        errors.append("missing meeting type metadata")
    if "**Q：" not in note_markdown and "**提问：" not in note_markdown:
        errors.append("expert-call smoke missing bold Q section")
    if not re.search(r"(?m)^【[^】]{1,60}】\S", note_markdown):
        errors.append("expert-call smoke missing bracketed answer topic")
    if re.search(r"(?m)^【[^】]{1,60}】\s*A[:：]", note_markdown):
        errors.append("expert-call smoke should not include A prefix after answer topic")
    errors.extend(contract.get("errors") or [])

    review_status = 0
    review_has_direct_editor = False
    review_has_confirm_button = False
    if review_url:
        review_status, review_html = get_local_page(review_url)
        review_has_direct_editor = "direct-editor" in review_html
        review_has_confirm_button = any(
            label in review_html
            for label in (
                "确认终稿并进入归档确认",
                "确认终稿，进入归档确认",
                "确认终稿并生成摘要/表格",
                "确认归档",
            )
        )
        if review_status != 200:
            errors.append(f"review page returned {review_status}")
        if not review_has_direct_editor:
            errors.append("review page missing direct-editor")
        if not review_has_confirm_button:
            errors.append("review page missing confirm button")

    history_status = 0
    drafts_status = 0
    if drafts_url:
        drafts_status, drafts_html = get_local_page(drafts_url)
        if drafts_status != 200:
            errors.append(f"drafts page returned {drafts_status}")
        if "待校对草稿" not in drafts_html:
            errors.append("drafts page content mismatch")

    if history_url:
        history_status, history_html = get_local_page(history_url)
        if history_status != 200:
            errors.append(f"history page returned {history_status}")
        if "历史" not in history_html and "会议纪要" not in history_html:
            errors.append("history page content mismatch")

    return {
        "ok": not errors,
        "errors": errors,
        "warnings": contract.get("warnings") or [],
        "workflow_run_id": response.get("workflow_run_id") or data.get("id") or "",
        "draft_id": draft_id,
        "review_url": review_url,
        "drafts_url": drafts_url,
        "history_url": history_url,
        "result_cache_url": url_path(str(outputs.get("result_cache_url") or "")),
        "review_status": review_status,
        "review_has_direct_editor": review_has_direct_editor,
        "review_has_confirm_button": review_has_confirm_button,
        "drafts_status": drafts_status,
        "history_status": history_status,
        "token_cleaned": False,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="临时创建 Dify Service API token，运行小样本回归并清理 token")
    parser.add_argument("--json", action="store_true", help="输出 JSON")
    parser.add_argument("--timeout", type=int, default=420, help="workflow blocking run 超时时间")
    parser.add_argument("--response-out", default="", help="可选：保存去敏后的原始响应 JSON")
    args = parser.parse_args()

    token_id = ""
    result: dict[str, Any] = {"ok": False, "errors": [], "warnings": []}
    started = time.time()
    try:
        token_id, token = create_temp_token()
        response = call_workflow(token, user="local-smoke-script-2026-05-09", timeout=args.timeout)
        if args.response_out:
            Path(args.response_out).expanduser().write_text(json.dumps(response, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        result = validate_response(response)
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        result = {"ok": False, "errors": [f"workflow http {exc.code}: {body[:500]}"], "warnings": []}
    except Exception as exc:
        result = {"ok": False, "errors": [str(exc)], "warnings": []}
    finally:
        cleaned = False
        if token_id:
            try:
                cleaned = delete_temp_token(token_id)
            except Exception as exc:
                result.setdefault("errors", []).append(f"temporary token cleanup failed: {exc}")
        result["token_cleaned"] = cleaned

    result["elapsed_sec"] = round(time.time() - started, 1)
    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        print("Dify Service API smoke:", "ok" if result.get("ok") else "failed")
        print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())
