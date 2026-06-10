#!/usr/bin/env python3
"""Export a reproducible local snapshot of the current Dify workflow graph."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import subprocess
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

DEFAULT_APP_ID = "8b8b90b1-432c-414a-842a-7426c628ae39"
DEFAULT_DB_CONTAINER = "docker-db_postgres-1"
DEFAULT_OUTPUT_ROOT = Path("/Users/kumaai/Documents/Codex/workspace/投资纪要工作流/03 Resources/dify-workflow-snapshots")


def now_stamp() -> str:
    return datetime.now().strftime("%Y-%m-%dT%H%M%S")


def sha256_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def run_psql(container: str, app_id: str) -> list[dict[str, Any]]:
    sql = f"""
    SELECT json_agg(row_to_json(t))::text
    FROM (
      SELECT
        id::text,
        app_id::text,
        type,
        version,
        graph,
        features,
        created_at::text,
        updated_at::text,
        marked_name,
        marked_comment,
        length(environment_variables) AS environment_variables_length,
        md5(environment_variables) AS environment_variables_md5
      FROM workflows
      WHERE app_id = '{app_id}'
      ORDER BY updated_at DESC
    ) t;
    """
    command = [
        "docker",
        "exec",
        container,
        "psql",
        "-U",
        "postgres",
        "-d",
        "dify",
        "-t",
        "-A",
        "-c",
        sql,
    ]
    result = subprocess.run(command, text=True, capture_output=True, timeout=30)
    if result.returncode != 0:
        raise RuntimeError(result.stderr.strip() or "psql export failed")
    text = result.stdout.strip()
    if not text:
        return []
    payload = json.loads(text)
    return payload or []


def parse_json_field(raw: str) -> Any:
    try:
        return json.loads(raw or "{}")
    except json.JSONDecodeError:
        return raw


def graph_nodes(graph: Any) -> list[dict[str, str]]:
    if not isinstance(graph, dict):
        return []
    nodes = graph.get("nodes") or []
    result: list[dict[str, str]] = []
    for node in nodes:
        if not isinstance(node, dict):
            continue
        data = node.get("data") if isinstance(node.get("data"), dict) else {}
        result.append(
            {
                "id": str(node.get("id") or ""),
                "type": str(data.get("type") or node.get("type") or ""),
                "title": str(data.get("title") or data.get("desc") or ""),
            }
        )
    return result


def write_snapshot(workflows: list[dict[str, Any]], output_dir: Path) -> dict[str, Any]:
    output_dir.mkdir(parents=True, exist_ok=True)
    manifest: dict[str, Any] = {
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "workflow_count": len(workflows),
        "workflows": [],
    }
    sanitized_workflows: list[dict[str, Any]] = []

    for workflow in workflows:
        graph_raw = workflow.get("graph") or "{}"
        features_raw = workflow.get("features") or "{}"
        graph = parse_json_field(graph_raw)
        features = parse_json_field(features_raw)
        safe_id = workflow["id"]
        version = re.sub(r"[^0-9A-Za-z._-]+", "-", str(workflow.get("version") or "unknown")).strip("-")
        graph_filename = f"workflow-{version}-{safe_id}.graph.json"
        features_filename = f"workflow-{version}-{safe_id}.features.json"

        (output_dir / graph_filename).write_text(
            json.dumps(graph, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        (output_dir / features_filename).write_text(
            json.dumps(features, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        manifest["workflows"].append(
            {
                "id": workflow.get("id"),
                "version": workflow.get("version"),
                "type": workflow.get("type"),
                "updated_at": workflow.get("updated_at"),
                "graph_file": graph_filename,
                "features_file": features_filename,
                "graph_sha256": sha256_text(graph_raw),
                "features_sha256": sha256_text(features_raw),
                "environment_variables_length": workflow.get("environment_variables_length"),
                "environment_variables_md5": workflow.get("environment_variables_md5"),
                "nodes": graph_nodes(graph),
            }
        )
        sanitized_workflows.append({k: v for k, v in workflow.items() if k not in {"graph", "features"}})

    (output_dir / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    (output_dir / "workflows.redacted.json").write_text(
        json.dumps(sanitized_workflows, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    readme_lines = [
        "# Dify 工作流快照",
        "",
        f"- 生成时间: {manifest['generated_at']}",
        f"- 工作流版本数量: {len(workflows)}",
        "- 环境变量不导出明文，只记录长度和 MD5 漂移哈希。",
        "",
        "## 工作流版本",
        "",
    ]
    for item in manifest["workflows"]:
        readme_lines.append(f"- `{item['version']}` `{item['id']}` updated `{item['updated_at']}`")
        readme_lines.append(f"  - graph: `{item['graph_file']}`")
        readme_lines.append(f"  - nodes: {len(item['nodes'])}")
    (output_dir / "README.md").write_text("\n".join(readme_lines) + "\n", encoding="utf-8")
    (output_dir.parent / "latest_snapshot.txt").write_text(str(output_dir) + "\n", encoding="utf-8")
    return manifest


def main() -> int:
    parser = argparse.ArgumentParser(description="导出 Dify workflow graph 快照")
    parser.add_argument("--app-id", default=DEFAULT_APP_ID, help="Dify app id")
    parser.add_argument("--db-container", default=DEFAULT_DB_CONTAINER, help="Postgres Docker container name")
    parser.add_argument("--output-root", default=str(DEFAULT_OUTPUT_ROOT), help="快照输出目录")
    parser.add_argument("--json", action="store_true", help="输出 JSON")
    args = parser.parse_args()

    output_dir = Path(args.output_root).expanduser() / now_stamp()
    try:
        workflows = run_psql(args.db_container, args.app_id)
        if not workflows:
            raise RuntimeError(f"未找到 app_id={args.app_id} 的 workflow")
        manifest = write_snapshot(workflows, output_dir)
    except Exception as exc:  # noqa: BLE001
        payload = {"ok": False, "error": str(exc)}
        if args.json:
            print(json.dumps(payload, ensure_ascii=False, indent=2))
        else:
            print(f"Dify workflow 快照导出失败: {exc}", file=sys.stderr)
        return 1

    payload = {"ok": True, "output_dir": str(output_dir), "workflow_count": manifest["workflow_count"]}
    if args.json:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
    else:
        print(f"已导出 Dify workflow 快照: {output_dir}")
        print(f"workflow_count: {manifest['workflow_count']}")
    return 0


if __name__ == "__main__":
    os.environ.setdefault("PYTHONUTF8", "1")
    raise SystemExit(main())
