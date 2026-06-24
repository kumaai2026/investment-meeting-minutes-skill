#!/usr/bin/env python3
"""Validate project custom agent TOML files for the expected Codex schema."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
AGENTS_DIR = REPO_ROOT / ".codex" / "agents"
EXPECTED = {"transcript_auditor", "content_integrity_reviewer"}


def parse_minimal_toml(text: str) -> dict[str, object]:
    """Parse the small TOML subset used by project custom agent files."""
    result: dict[str, object] = {}
    lines = text.splitlines()
    index = 0
    while index < len(lines):
        raw = lines[index]
        stripped = raw.strip()
        index += 1
        if not stripped or stripped.startswith("#") or stripped.startswith("["):
            continue
        if "=" not in stripped:
            continue
        key, value = stripped.split("=", 1)
        key = key.strip()
        value = value.strip()
        if value.startswith('"""'):
            chunks = []
            value = value[3:]
            if value.endswith('"""'):
                result[key] = value[:-3]
                continue
            if value:
                chunks.append(value)
            while index < len(lines):
                line = lines[index]
                index += 1
                if line.endswith('"""'):
                    chunks.append(line[:-3])
                    break
                chunks.append(line)
            result[key] = "\n".join(chunks)
        elif value.startswith('"') and value.endswith('"'):
            result[key] = value[1:-1]
        else:
            result[key] = value
    return result


def validate() -> dict[str, object]:
    errors: list[str] = []
    files = sorted(AGENTS_DIR.glob("*.toml"))
    names = set()
    for path in files:
        payload = parse_minimal_toml(path.read_text(encoding="utf-8"))
        for field in ("name", "description", "developer_instructions"):
            if field not in payload:
                errors.append(f"{path}: missing {field}")
        if "default_prompt" in payload:
            errors.append(f"{path}: default_prompt is deprecated")
        if payload.get("sandbox_mode") != "read-only":
            errors.append(f"{path}: sandbox_mode must be read-only")
        if "model" in payload:
            errors.append(f"{path}: custom agent must not hardcode model")
        name = str(payload.get("name") or "")
        names.add(name)
        if name not in EXPECTED:
            errors.append(f"{path}: unexpected agent name {name}")
    missing = sorted(EXPECTED - names)
    if missing:
        errors.append(f"missing expected agents: {', '.join(missing)}")
    extra_files = [str(path) for path in files if path.stem not in {"transcript-auditor", "content-integrity-reviewer"}]
    if extra_files:
        errors.append(f"unexpected agent files: {', '.join(extra_files)}")
    return {"ok": not errors, "errors": errors, "warnings": [], "agent_count": len(files)}


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate Codex custom agent static schema")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()
    result = validate()
    print(json.dumps(result, ensure_ascii=False, indent=2) if args.json else result)
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
