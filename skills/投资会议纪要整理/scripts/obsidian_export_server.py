#!/usr/bin/env python3
"""Local HTTP bridge for Dify -> Obsidian Markdown/Word export."""

from __future__ import annotations

import cgi
import json
import os
import sys
import tempfile
import traceback
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
LOG_DIR = Path("/Users/kumaai/Library/Logs/kumaai-sync")
DEFAULT_HOST = "0.0.0.0"
DEFAULT_PORT = 8766

sys.path.insert(0, str(SCRIPT_DIR))
from archive_raw_inputs import archive_files  # noqa: E402
from export_to_obsidian import DEFAULT_VAULT_DIR, export_note, normalize_meeting_date, sync_vault_to_gdrive  # noqa: E402


def _json_response(handler: BaseHTTPRequestHandler, status: int, payload: dict) -> None:
    data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    handler.send_response(status)
    handler.send_header("Content-Type", "application/json; charset=utf-8")
    handler.send_header("Content-Length", str(len(data)))
    handler.end_headers()
    handler.wfile.write(data)


class ObsidianExportHandler(BaseHTTPRequestHandler):
    server_version = "ObsidianExportBridge/1.0"

    def log_message(self, fmt: str, *args) -> None:
        LOG_DIR.mkdir(parents=True, exist_ok=True)
        with (LOG_DIR / "obsidian-export-server.log").open("a", encoding="utf-8") as handle:
            handle.write("%s - %s\n" % (self.log_date_time_string(), fmt % args))

    def do_GET(self) -> None:
        if self.path.rstrip("/") == "/health":
            _json_response(self, 200, {"ok": True, "service": "obsidian-export"})
            return
        _json_response(self, 404, {"ok": False, "error": "not found"})

    def do_POST(self) -> None:
        route = self.path.rstrip("/")
        if route == "/archive-inputs":
            self._handle_archive_inputs()
            return
        if route != "/export":
            _json_response(self, 404, {"ok": False, "error": "not found"})
            return

        length = int(self.headers.get("Content-Length", "0") or "0")
        if length <= 0:
            _json_response(self, 400, {"ok": False, "error": "empty request body"})
            return

        try:
            payload = json.loads(self.rfile.read(length).decode("utf-8"))
        except Exception as exc:
            _json_response(self, 400, {"ok": False, "error": f"invalid json: {exc}"})
            return

        markdown = str(payload.get("markdown") or "").strip()
        meeting_date = str(payload.get("meeting_date") or "").strip() or None
        if not markdown.startswith("#"):
            _json_response(self, 400, {"ok": False, "error": "markdown must start with a heading"})
            return

        try:
            with tempfile.TemporaryDirectory(prefix="dify-obsidian-export-") as tmp:
                source = Path(tmp) / "meeting.md"
                source.write_text(markdown + "\n", encoding="utf-8")
                result = export_note(source, Path("/Users/kumaai/Documents/Codex/workspace/投资纪要工作流/01 Projects/会议纪要"), meeting_date)
            ok = result.md_created and result.docx_created
            _json_response(
                self,
                200 if ok else 500,
                {
                    "ok": ok,
                    "markdown_path": str(result.md_path),
                    "word_path": str(result.docx_path),
                    "markdown_created": result.md_created,
                    "word_created": result.docx_created,
                    "google_drive_synced": result.sync_created,
                    "messages": {
                        "markdown": result.md_message,
                        "word": result.docx_message,
                        "google_drive": result.sync_message,
                    },
                },
            )
        except Exception as exc:
            self.log_message("export failed: %s\n%s", exc, traceback.format_exc())
            _json_response(self, 500, {"ok": False, "error": str(exc)})

    def _handle_archive_inputs(self) -> None:
        content_type = self.headers.get("Content-Type", "")
        if "multipart/form-data" not in content_type:
            _json_response(self, 400, {"ok": False, "error": "multipart/form-data required"})
            return

        form = cgi.FieldStorage(fp=self.rfile, headers=self.headers, environ={"REQUEST_METHOD": "POST"})
        meeting_date = normalize_meeting_date(form.getfirst("meeting_date", ""))
        meeting_title = str(
            form.getfirst("meeting_title", "")
            or form.getfirst("title", "")
            or form.getfirst("custom_meeting_title", "")
            or ""
        ).strip()
        archived_paths: list[str] = []

        try:
            with tempfile.TemporaryDirectory(prefix="dify-raw-inputs-") as tmp:
                tmp_dir = Path(tmp)
                local_files: list[Path] = []
                for field_name in ("meeting_file", "audio_file"):
                    item = form[field_name] if field_name in form else None
                    if item is None:
                        continue
                    items = item if isinstance(item, list) else [item]
                    for current in items:
                        filename = Path(getattr(current, "filename", "") or "").name
                        if not filename:
                            continue
                        target = tmp_dir / filename
                        target.write_bytes(current.file.read())
                        local_files.append(target)

                if local_files:
                    archived_paths = [
                        str(path)
                        for path in archive_files(
                            local_files,
                            Path("/Users/kumaai/Documents/Codex/workspace/投资纪要工作流/00 Inbox/会议原始记录"),
                            meeting_date,
                            meeting_title or None,
                        )
                    ]

            if archived_paths:
                google_drive_synced, google_drive_message = sync_vault_to_gdrive(DEFAULT_VAULT_DIR)
            else:
                google_drive_synced = False
                google_drive_message = "跳过同步：无上传文件需要归档"

            _json_response(
                self,
                200,
                {
                    "ok": True,
                    "meeting_date": meeting_date,
                    "archived_paths": archived_paths,
                    "archived_count": len(archived_paths),
                    "google_drive_synced": google_drive_synced,
                    "google_drive_message": google_drive_message,
                },
            )
        except Exception as exc:
            self.log_message("archive-inputs failed: %s\n%s", exc, traceback.format_exc())
            _json_response(self, 500, {"ok": False, "error": str(exc), "archived_paths": archived_paths})


def main() -> int:
    host = os.environ.get("OBSIDIAN_EXPORT_BRIDGE_HOST", DEFAULT_HOST)
    port = int(os.environ.get("OBSIDIAN_EXPORT_BRIDGE_PORT", str(DEFAULT_PORT)))
    server = ThreadingHTTPServer((host, port), ObsidianExportHandler)
    print(f"Obsidian export bridge listening on http://{host}:{port}", flush=True)
    server.serve_forever()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
