#!/usr/bin/env python3
"""Patch the local Dify meeting-minutes workflow for Fun-ASR-Nano auxiliary ASR."""

from __future__ import annotations

import argparse
import json
import subprocess
from datetime import datetime
from pathlib import Path
from typing import Any


DEFAULT_APP_ID = "8b8b90b1-432c-414a-842a-7426c628ae39"
DEFAULT_DB_CONTAINER = "docker-db_postgres-1"
DEFAULT_BACKUP_DIR = Path("/Users/kumaai/Documents/Codex/workspace/投资纪要工作流/03 Resources/dify-workflow-snapshots")


MERGE_CODE = r'''import difflib
import json
import re

MAX_SEGMENTS = 8

def _to_text(value):
    if value is None:
        return ""
    if isinstance(value, list):
        return "\n\n".join(str(item).strip() for item in value if str(item).strip())
    return str(value).strip()

def _segments(text):
    text = re.sub(r"[ \t]+", " ", str(text or "")).strip()
    raw = re.split(r"(?<=[。！？!?；;])\s*|\n+", text)
    result = []
    for item in raw:
        item = item.strip()
        if len(item) >= 12:
            result.append(item)
        if len(result) >= 80:
            break
    return result

def _weakly_covered(source_segments, target_text):
    target = str(target_text or "")
    target_segments = _segments(target)
    findings = []
    for seg in source_segments[:80]:
        if seg in target:
            continue
        best = 0.0
        for other in target_segments[:80]:
            best = max(best, difflib.SequenceMatcher(None, seg[:160], other[:160]).ratio())
            if best >= 0.72:
                break
        if best < 0.58:
            findings.append(seg[:120] + ("..." if len(seg) > 120 else ""))
        if len(findings) >= MAX_SEGMENTS:
            break
    return findings

def _bullet(items, empty):
    if not items:
        return f"- {empty}"
    return "\n".join("- " + item for item in items)

def _payload_text(payload, *keys):
    for key in keys:
        value = payload.get(key)
        if isinstance(value, dict):
            nested = value.get("text") or value.get("fun_asr_nano")
            if nested:
                return _to_text(nested)
        text = _to_text(value)
        if text:
            return text
    aux = payload.get("auxiliary_transcripts")
    if isinstance(aux, dict):
        nano = aux.get("fun_asr_nano")
        if isinstance(nano, dict):
            return _to_text(nano.get("text"))
        return _to_text(nano)
    return ""

def _cross_check_summary(text_reference, sensevoice_text, sensevoice_status, nano_text, nano_status, asr_comparison_summary):
    lines = []
    if text_reference and sensevoice_text:
        text_only = _weakly_covered(_segments(text_reference), sensevoice_text)
        audio_only = _weakly_covered(_segments(sensevoice_text), text_reference)
        lines.append("【交叉校对提示】")
        lines.append("- 已同时检测到原始文字/文稿和 SenseVoice 音频转录，第一次人工校对应以人工修订后的合并稿为准。")
        lines.append(f"- 原始文字/文稿长度：{len(text_reference)} 字；SenseVoice 转录长度：{len(sensevoice_text)} 字；SenseVoice 状态：{sensevoice_status}。")
        lines.append("- 文字中可能未被音频稳定覆盖的片段：")
        lines.append(_bullet(text_only, "未发现明显缺口"))
        lines.append("- 音频转录中可能未出现在文字稿的片段：")
        lines.append(_bullet(audio_only, "未发现明显新增片段"))
    elif sensevoice_text:
        lines.append(f"【交叉校对提示】\n- 仅检测到音频转录，SenseVoice 状态：{sensevoice_status}。请在第一次人工校对时重点校准发言人、公司名、数字、比例和疑似 ASR 词。")
    elif text_reference:
        lines.append("【交叉校对提示】\n- 仅检测到原始文字/文稿，直接进入第一次人工校对。请校准发言人、公司名、股票代码、数字、比例和自然段切分。")
    else:
        lines.append("【交叉校对提示】\n- 未检测到有效输入，请在第一次人工校对页补充转录文本。")
    if nano_text:
        lines.append(f"- Fun-ASR-Nano-2512 辅助转录长度：{len(nano_text)} 字；状态：{nano_status or '已返回辅助文本'}。")
        lines.append("- Nano 只作为辅助校验来源。公司名、股票代码、数字、英文缩写和金融术语与 SenseVoice 冲突时，不要自动改写，必须在初校稿保留并标注。")
    if asr_comparison_summary:
        lines.append("【SenseVoice vs Fun-ASR-Nano 差异摘要】\n" + asr_comparison_summary[:4000])
    lines.append("- 标的名称、股票代码、行业和 A 股知识需要用 a-stock-data / 本地代码表核验；ASR 结果不能单独作为写入代码的依据。")
    return "\n".join(lines).strip()

def main(pasted_text, document_text, sensevoice_body):
    pasted = _to_text(pasted_text)
    document = _to_text(document_text)
    body = _to_text(sensevoice_body)
    sensevoice_text = ""
    fun_asr_nano_text = ""
    asr_comparison_summary = ""
    sensevoice_status = "未上传音频"
    nano_status = ""
    if body:
        try:
            payload = json.loads(body)
            sensevoice_text = _to_text(payload.get("text") or payload.get("sensevoice_transcript") or payload.get("audio_text"))
            fun_asr_nano_text = _payload_text(payload, "fun_asr_nano_transcript", "auxiliary_text")
            nano_status = _to_text(payload.get("auxiliary_status"))
            asr_comparison_summary = _to_text(payload.get("asr_comparison_summary") or payload.get("asr_comparison_diff"))
            if payload.get("ok") and sensevoice_text:
                sensevoice_status = "SenseVoice 转录成功"
            elif payload.get("ok"):
                sensevoice_status = "未上传音频或音频为空"
            else:
                sensevoice_status = "SenseVoice 转录失败：" + _to_text(payload.get("error"))[:300]
        except Exception:
            sensevoice_status = "SenseVoice 返回无法解析"
            sensevoice_text = body
    text_sources = []
    if pasted:
        text_sources.append("【直接粘贴文本】\n" + pasted)
    if document:
        text_sources.append("【上传文稿解析文本】\n" + document)
    text_reference = "\n\n".join(text_sources).strip()
    parts = []
    if text_reference:
        parts.append("【原始文本/文稿】\n" + text_reference)
    if sensevoice_text:
        parts.append("【SenseVoice 音频转录】\n" + sensevoice_text)
    combined_text = "\n\n".join(parts).strip()
    if text_reference and sensevoice_text:
        input_mode = "音频+文本：必须先交叉校对后再进入整理"
    elif sensevoice_text:
        input_mode = "音频：请基于 SenseVoice 主转录做第一次人工校对，并参考 Fun-ASR-Nano 辅助结果"
    elif text_reference:
        input_mode = "文本：直接进入第一次人工校对"
    else:
        input_mode = "无有效输入"
    cross_check_summary = _cross_check_summary(
        text_reference,
        sensevoice_text,
        sensevoice_status,
        fun_asr_nano_text,
        nano_status,
        asr_comparison_summary,
    )
    return {
        "text_reference": text_reference,
        "sensevoice_transcript": sensevoice_text,
        "fun_asr_nano_transcript": fun_asr_nano_text,
        "asr_comparison_summary": asr_comparison_summary,
        "sensevoice_status": sensevoice_status,
        "combined_text": combined_text,
        "input_mode": input_mode,
        "cross_check_summary": cross_check_summary,
    }
'''


PROMPT_INSERT = '''\n- Fun-ASR-Nano-2512 辅助转录：{{#1779200000001.fun_asr_nano_transcript#}}\n- ASR 差异摘要：{{#1779200000001.asr_comparison_summary#}}\n'''

PROMPT_SECTION = '''\n【Fun-ASR-Nano-2512 辅助转录，只用于交叉校验】\n{{#1779200000001.fun_asr_nano_transcript#}}\n\n【SenseVoice vs Fun-ASR-Nano 差异摘要】\n{{#1779200000001.asr_comparison_summary#}}\n'''

PROMPT_RULE = '''\n【ASR 与金融校验规则】\n- SenseVoice 是主转录来源，Fun-ASR-Nano-2512 是辅助对照来源；两者冲突时不得自动替换，必须保留不稳妥片段并写入存疑。\n- 对公司名、股票代码、行业、A 股金融知识和英文缩写，必须使用可用的 a-stock-data 能力、本地代码表或 review bridge MCP 工具核验；ASR 结果不能单独作为写入代码的依据。\n- Nano 更像术语时可以作为候选提示，但只有通过代码/资料核验后才能写成确定项。\n'''


def run_psql(container: str, sql: str) -> str:
    command = ["docker", "exec", "-i", container, "psql", "-U", "postgres", "-d", "dify", "-t", "-A"]
    result = subprocess.run(command, input=sql, text=True, capture_output=True, timeout=60)
    if result.returncode != 0:
        raise RuntimeError(result.stderr.strip() or "psql failed")
    return result.stdout.strip()


def load_workflows(container: str, app_id: str) -> list[dict[str, Any]]:
    sql = f"""
    SELECT json_agg(row_to_json(t))::text
    FROM (
      SELECT id::text, version, type, graph, updated_at::text
      FROM workflows
      WHERE app_id = '{app_id}'
      ORDER BY updated_at DESC
    ) t;
    """
    text = run_psql(container, sql)
    return json.loads(text or "[]") or []


def selected_workflows(workflows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    draft = next((item for item in workflows if str(item.get("version")) == "draft"), None)
    published = next((item for item in workflows if str(item.get("version")) != "draft"), None)
    return [item for item in (draft, published) if item]


def node_outputs(data: dict[str, Any]) -> dict[str, Any]:
    outputs = data.get("outputs")
    if not isinstance(outputs, dict):
        outputs = {}
        data["outputs"] = outputs
    return outputs


def patch_merge_node(node: dict[str, Any]) -> bool:
    data = node.get("data") if isinstance(node.get("data"), dict) else {}
    if node.get("id") != "1779200000001":
        return False
    data["title"] = "合并：文本与 SenseVoice/Nano 转录并生成交叉校对提示"
    data["code"] = MERGE_CODE
    outputs = node_outputs(data)
    outputs.setdefault("fun_asr_nano_transcript", {"type": "string"})
    outputs.setdefault("asr_comparison_summary", {"type": "string"})
    return True


def patch_http_node(node: dict[str, Any]) -> bool:
    data = node.get("data") if isinstance(node.get("data"), dict) else {}
    if node.get("id") != "1779120000002":
        return False
    data["title"] = "本地音视频转录兜底：SenseVoice + Fun-ASR-Nano"
    body = data.get("body") if isinstance(data.get("body"), dict) else {}
    for item in body.get("data") or []:
        if isinstance(item, dict) and item.get("key") == "asr_model":
            item["value"] = "自动：SenseVoiceSmall；Fun-ASR-Nano-2512 辅助对照；失败回退 Whisper medium"
    return True


def patch_skill_prompt(node: dict[str, Any]) -> bool:
    data = node.get("data") if isinstance(node.get("data"), dict) else {}
    if node.get("id") != "1778820515971":
        return False
    changed = False
    for field in ("instruction", "prompt", "tool_configurations", "tool_parameters"):
        value = data.get(field)
        if isinstance(value, str):
            new_value = patch_prompt_text(value)
            if new_value != value:
                data[field] = new_value
                changed = True
        elif isinstance(value, dict):
            changed = patch_prompt_dict(value) or changed
    return changed


def patch_prompt_dict(value: dict[str, Any]) -> bool:
    changed = False
    for key, item in list(value.items()):
        if isinstance(item, str):
            new_item = patch_prompt_text(item)
            if new_item != item:
                value[key] = new_item
                changed = True
        elif isinstance(item, dict):
            changed = patch_prompt_dict(item) or changed
        elif isinstance(item, list):
            for child in item:
                if isinstance(child, dict):
                    changed = patch_prompt_dict(child) or changed
    return changed


def patch_prompt_text(text: str) -> str:
    if "Fun-ASR-Nano-2512 辅助转录" in text and "ASR 与金融校验规则" in text:
        return text
    result = text
    marker = "- SenseVoice 状态：{{#1779200000001.sensevoice_status#}}\n"
    if marker in result and "fun_asr_nano_transcript" not in result:
        result = result.replace(marker, marker + PROMPT_INSERT, 1)
    section_marker = "【合并输入，作为正文整理主来源】\n{{#1779200000001.combined_text#}}\n"
    if section_marker in result and "Fun-ASR-Nano-2512 辅助转录，只用于交叉校验" not in result:
        result = result.replace(section_marker, section_marker + PROMPT_SECTION, 1)
    history_marker = "【历史纪要参考，只可用于名称/代码/术语校验，不得压缩本次原文】"
    if history_marker in result and "ASR 与金融校验规则" not in result:
        result = result.replace(history_marker, PROMPT_RULE + "\n" + history_marker, 1)
    return result


def patch_graph(graph: dict[str, Any]) -> tuple[dict[str, Any], list[str]]:
    changed: list[str] = []
    for node in graph.get("nodes") or []:
        if not isinstance(node, dict):
            continue
        if patch_merge_node(node):
            changed.append("merge-node")
        if patch_http_node(node):
            changed.append("local-transcribe-node")
        if patch_skill_prompt(node):
            changed.append("skill-agent-prompt")
    return graph, changed


def backup_graph(workflow: dict[str, Any], graph: dict[str, Any], backup_dir: Path) -> Path:
    backup_dir.mkdir(parents=True, exist_ok=True)
    path = backup_dir / f"pre-funasr-nano-{workflow['version']}-{workflow['id']}.graph.json"
    path.write_text(json.dumps(graph, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return path


def update_workflow(container: str, workflow_id: str, graph: dict[str, Any]) -> None:
    graph_text = json.dumps(graph, ensure_ascii=False)
    escaped = graph_text.replace("'", "''")
    sql = f"UPDATE workflows SET graph = '{escaped}', updated_at = NOW() WHERE id = '{workflow_id}';"
    run_psql(container, sql)


def main() -> int:
    parser = argparse.ArgumentParser(description="更新本地 Dify 会议纪要 workflow，接入 Fun-ASR-Nano 辅助转录")
    parser.add_argument("--app-id", default=DEFAULT_APP_ID)
    parser.add_argument("--db-container", default=DEFAULT_DB_CONTAINER)
    parser.add_argument("--backup-root", default=str(DEFAULT_BACKUP_DIR))
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    workflows = load_workflows(args.db_container, args.app_id)
    targets = selected_workflows(workflows)
    stamp = datetime.now().strftime("%Y-%m-%dT%H%M%S")
    backup_dir = Path(args.backup_root).expanduser() / f"{stamp}-pre-funasr-nano-db-patch"
    results: list[dict[str, Any]] = []
    for workflow in targets:
        graph = json.loads(workflow.get("graph") or "{}")
        backup_path = backup_graph(workflow, graph, backup_dir)
        patched_graph, changed = patch_graph(graph)
        if changed and not args.dry_run:
            update_workflow(args.db_container, workflow["id"], patched_graph)
        results.append(
            {
                "id": workflow["id"],
                "version": workflow.get("version"),
                "changed": sorted(set(changed)),
                "backup": str(backup_path),
                "updated": bool(changed and not args.dry_run),
            }
        )
    payload = {"ok": True, "dry_run": bool(args.dry_run), "workflow_count": len(results), "results": results}
    if args.json:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
    else:
        for item in results:
            print(f"{item['version']} {item['id']}: {', '.join(item['changed']) or 'no change'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
