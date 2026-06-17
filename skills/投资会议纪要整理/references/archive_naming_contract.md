# Archive Naming Contract

Use this file when archiving raw meeting inputs or exporting confirmed meeting notes. The naming contract is deterministic so local runs, Dify runs, Google Drive sync, and later manual review use the same paths.

## Raw Input Archive

Archive root:

```text
/Users/kumaai/Documents/Codex/workspace/投资纪要工作流/00 Inbox/会议原始记录
```

Folder pattern:

```text
YYYY-MM-DD/YYYY-MM-DD - 会议标题/
```

Raw file pattern:

```text
YYYY-MM-DD - 会议标题 - 原始NN-材料类型.扩展名
```

Allowed material labels:

- `文稿`
- `录音`
- `录像`
- `附件`

Examples:

```text
2026-06-17/2026-06-17 - AI数据中心液冷产业链交流/
2026-06-17 - AI数据中心液冷产业链交流 - 原始01-文稿.docx
2026-06-17 - AI数据中心液冷产业链交流 - 原始02-录音.mp3
2026-06-17 - AI数据中心液冷产业链交流 - 原始03-附件.pdf
```

Rules:

- Copy raw files; do not move or delete user originals.
- Use the meeting date when known; otherwise use the current date.
- Use `YYYY-MM-DD` only. Reject malformed dates.
- Infer a title from the first non-empty DOCX paragraph or TXT/MD line only when no title is passed.
- Do not keep generic export names such as `export_*.mp3` when a title is known or inferable.
- Replace invalid filename characters `\ / : * ? " < > |` with `-`.
- Collapse repeated whitespace.
- Truncate very long titles before building filenames.
- Preserve all collisions by adding a timestamp or numeric suffix; never overwrite.
- Use `scripts/archive_raw_inputs.py --dry-run --json ...` before irreversible archive writes in automation.

## Final Note Archive

Default final-note root:

```text
/Users/kumaai/Documents/Codex/workspace/投资纪要工作流/01 Projects/会议纪要
```

Final-note folder:

```text
YYYY-MM-DD/
```

Preferred final-note filename:

```text
YYYY-MM-DD - 会议标题 - 会议类型.md
YYYY-MM-DD - 会议标题 - 会议类型.docx
```

If the title already includes the meeting type, do not repeat the meeting type. If the filename collides, append a timestamp suffix and keep both files.

Do not expose raw archive paths or technical archive status in the human-readable note body.
