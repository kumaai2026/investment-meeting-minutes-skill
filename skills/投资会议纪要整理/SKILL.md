---
name: investment-meeting-minutes
description: "Use when Codex needs to turn a Chinese investment meeting recording, transcript, or mixed audio+text input into a strict Markdown meeting note with speaker segmentation, company-name correction, stock-symbol validation, source-file archiving, and Markdown/Word export. Triggers include: 整理会议录音, 整理投资会议纪要, 把这段转录整理成纪要, 输出 Obsidian 会议纪要, 校对公司名称和股票代码, 导出 md 和 word, 结合录音与文字整理, 按发言人/板块/标的分段."
---

# Investment Meeting Minutes

## Overview

Produce a strict, repeatable investment meeting note for Chinese-language meetings. Archive all raw input files by date, keep the original wording as much as practical, remove only meaningless filler words and meaningless repeated words, split by speaker + sector + symbol, validate company names and stock codes, and export the human-confirmed Markdown + Word into the user's Obsidian workflow. In the Dify localhost workflow, there are two mandatory human gates: initial transcript review before the meeting-minutes skill runs, and final note review after the skill runs. Structured summary/table artifacts are generated only after final-note confirmation, and formal archive/knowledge-base sync happens only after archive confirmation.

## Workflow

### 0. UTF-8 encoding guardrails

All Chinese text in this skill and all intermediate/final text artifacts must be read and written as UTF-8.

Cross-platform import rules:
- `SKILL.md` must be UTF-8 without BOM and must start with `---` as the first three bytes of the file. Do not save it as Windows ANSI, GBK, GB2312, Big5, or UTF-8 with BOM.
- Keep `SKILL.md` line endings as LF. Windows editors may display and edit LF files normally; do not convert the skill package to CRLF during export or import.
- When moving the skill package between macOS, Linux, and Windows, use ZIP tools that preserve UTF-8 filenames. If a Windows tool shows Chinese folder names as mojibake, use the ASCII frontmatter `name` or the ASCII alias directory `investment-meeting-minutes` where available.
- Type skills should reference the base skill by relative package relationship, for example “read the base skill in the same skill package: `投资会议纪要整理` / `investment-meeting-minutes`”. Do not make a type skill depend on a macOS-only absolute path.
- Local paths in this document are deployment defaults for the current macOS Dify instance. On Windows or another host, map them to that machine's configured workflow root, archive root, and review/export service URLs instead of copying the literal `/Users/kumaai/...` paths.
- Before importing or syncing a skill package on any system, run `python3 scripts/validate_utf8_text.py SKILL.md --require-cjk --portable-skill` or an equivalent UTF-8/no-BOM/LF check.

Hard rules:
- For Python file I/O, always pass `encoding="utf-8"` for Markdown, TXT, CSV, JSON, TSV, SRT, VTT, YAML, logs, and extracted DOCX text.
- When a subprocess may print or consume Chinese text, run it with a UTF-8 environment when practical: `PYTHONUTF8=1`, `PYTHONIOENCODING=utf-8`, and `LC_ALL`/`LANG` set to a UTF-8 locale such as `en_US.UTF-8` or `zh_CN.UTF-8`.
- Do not rely on platform default encodings. Do not use implicit `open()`, `Path.read_text()`, or `Path.write_text()` for Chinese text.
- If a file fails UTF-8 decoding, stop using that text as a source, report the file path and error, then try a known source format such as DOCX XML extraction or the original audio. Do not silently replace invalid characters.

Encoding validation:
- Before final export, validate the finished Markdown with `scripts/validate_utf8_text.py NOTE.md --require-cjk`.
- After export, validate both final artifacts with `scripts/validate_utf8_text.py OUTPUT.md OUTPUT.docx --require-cjk`.
- If validation fails, fix the source encoding or regenerate the artifact before delivery. Never deliver a note with mojibake, replacement characters (`U+FFFD`), or unreadable Chinese.

### 1. Archive and inspect the inputs

Before transcription or writing, archive every raw file provided for this meeting.

Raw-file archive rules:
- Archive target: `/Users/kumaai/Documents/Codex/workspace/投资纪要工作流/00 Inbox/会议原始记录`.
- Create or use a date folder under the archive target. Prefer the meeting date if known; otherwise use the current system date in `YYYY-MM-DD` format.
- Under the date folder, create one meeting-session folder per meeting using `YYYY-MM-DD - 会议标题`. Same-day meetings must not share a flat raw-file directory.
- Copy all source files used for the note into that meeting-session folder before processing. Do not delete or move the user's originals.
- Archived raw files must use the standard filename pattern `YYYY-MM-DD - 会议标题 - 原始NN-材料类型.扩展名`, for example `2026-05-13 - AI数据中心温控企业海外拓展与市场策略交流 - 原始01-文稿.docx` and `2026-05-13 - AI数据中心温控企业海外拓展与市场策略交流 - 原始02-录音.mp3`. Material types should use `文稿`, `录音`, `录像`, or `附件`. If the title is not passed explicitly, `archive_raw_inputs.py` should infer it from the first non-empty DOCX paragraph or first TXT/MD line when possible; only fall back to a cleaned source filename when no title can be inferred. Do not keep generic WeChat or export names such as `export_*.mp3` as the final archive filename when a title is known or inferable.
- If filenames collide, preserve both files by adding a timestamp or numeric suffix.
- Do not expose raw-file archive details in the final note body. Store source-file details in draft metadata and logs; the final human-readable note should not include process fields such as `输入来源` or `整理说明`.

Use `scripts/archive_raw_inputs.py` when raw files are available.

Example:

```bash
python3 scripts/archive_raw_inputs.py INPUT.docx INPUT.mp3 --date 2026-04-28 --title "会议标题"
```

Handle these cases:
- Audio only: transcribe first, then organize.
- Text only: organize directly.
- Audio + text: use the transcript as the primary source and use the text as a correction reference.
- In the Dify workflow on `localhost:81`, the required chain is: upload files -> fill meeting title and choose meeting type -> text extraction or SenseVoice transcription -> human initial review -> meeting-minutes skill generation -> human second review -> final-note confirmation -> generate structured summary and target table -> archive confirmation. The initial review creates a `pre_agent` draft at the local review server before any type skill is allowed to run. Confirming that initial review triggers a second Dify workflow run with `input_reviewed=true`, then the selected meeting-type skill runs and creates the `post_agent` second-review draft. Confirming the second-review draft writes `final.md` in the draft store and generates post-review artifacts, but it still does not write the formal Obsidian archive or Dify knowledge base until `/confirm-archive` is submitted.
- When this skill is invoked by the Dify Skill Agent plugin, the upstream `combined_text`, `text_reference`, and `sensevoice_transcript` fields are already valid meeting materials. Do not ask the user to upload or paste materials again. The Skill Agent may run the selected type skill only when the system field `input_reviewed` is true. If `input_reviewed` is missing or false, return only a minimal initial-review placeholder and do not execute meeting-note formatting. In the Dify plugin, the tool-call `skill_name` should use the selected local folder name such as `投资会议纪要-多人复盘会`; the frontmatter name `investment-meeting-minutes` is metadata only. For Dify, review/export/sync are downstream nodes, so generate the draft Markdown and do not run final export scripts inside the Skill Agent call.
- Dify raw-file archiving calls `http://host.docker.internal:8766/archive-inputs`. When uploaded raw files are archived, that bridge must trigger the Google Drive sync script in the background and return `google_drive_synced` plus `google_drive_message` for the Dify output.

When audio is provided:
- First use SenseVoice through the local FunASR runtime as the primary transcript.
- Use Fun-ASR-Nano-2512 as an auxiliary transcript for cross-checking finance terms, company names, stock codes, numbers, and English abbreviations. Do not replace the primary transcript automatically only because Nano differs; surface conflicts for human review.
- Use `scripts/transcribe_audio.py` as the standard entry point. Its default `--engine auto` tries SenseVoice first and falls back to Whisper only when SenseVoice/FunASR is unavailable. Use `--engine fun-asr-nano --nano-hub ms --nano-model FunAudioLLM/Fun-ASR-Nano-2512` for the auxiliary model or comparison runs.
- Keep Nano runtime isolated when possible. The local deployment may set `FUNASR_NANO_PYTHON` to a Nano-specific virtualenv and `FUNASR_MODEL_CACHE` to a local model cache; do not vendor model weights or virtualenv contents into a reusable GitHub skill package.
- For Dify, keep the local LaunchAgent `com.kumaai.sensevoice-transcription-server` running. It serves `scripts/sensevoice_transcription_server.py` at `http://host.docker.internal:8765/transcribe` for the Dify HTTP node. The review bridge `/dify/transcribe-files` returns `sensevoice_transcript` plus `fun_asr_nano_transcript` when the auxiliary model is available.
- Default SenseVoice model: `iic/SenseVoiceSmall`; default auxiliary model: `FunAudioLLM/Fun-ASR-Nano-2512`; default language: `zh` for SenseVoice and `中文` for Nano; default output: `.txt`.
- If the user needs timestamp formats such as `vtt`/`srt`/`tsv`, run `scripts/transcribe_audio.py --engine whisper --output-format vtt|srt|tsv`.
- For Whisper fallback, quality is first priority: do not use `small`/`base`/`tiny` unless explicitly approved by the user; default to at least `medium`.
- If local ASR is unavailable, tell the user clearly what is missing and continue with any provided text instead of blocking the whole workflow.

### 2. Preprocess before writing

Use `scripts/process_transcript.py` when the text is long, noisy, or missing clear speaker boundaries.

Example:

```bash
python3 scripts/process_transcript.py INPUT.txt --speakers 张三,李四,主持人
```

The preprocessing result is only an aid. Do not ship it as the final note without restructuring.

### 3. Correct names and symbols

Read these references when needed:
- `references/default_output_template.md`
- `references/output_format_guide.md`
- `references/word_export_style_reference.md`
- `references/proofreading_guide.md`
- `references/symbol_sources.md`

Correction rules:
- Correct company names, sectors, people, and finance terminology from context.
- Validate symbols before writing them into the final note.
- For target names, stock codes, sectors, and A-share financial knowledge, call the local `a-stock-data` capability when available, especially its symbol lookup, quote, resolve-targets, and stock-profile tools exposed by the review bridge. Use it together with the local symbol resources; never use ASR text alone to assign a code.
- Prefer Chinese investment context when choosing between multiple listings.
- Use A-share first for typical mainland research context, then Hong Kong, then US, unless the source explicitly points elsewhere.
- If you cannot confirm a name or code, mark it in the ambiguity section instead of guessing.
- For uncertain proper nouns in source text, actively verify against available resources (local symbol resources, company disclosures, or reliable web sources) before finalizing.
- Use `scripts/query_symbol_candidates.py` for local candidate lookup before writing a stock code. Only write a code when the result is `confirmed`; if the result is `ambiguous` or `not_found`, keep the source wording and add it to `## 二、存疑与待确认`.

Symbol-source rules:
- The GitHub repo `LondonMarket/Global-Stock-Symbols` is useful for US/HK/global coverage, but it does not cover mainland A-share tickers in the expected `.SH` / `.SZ` / `.BJ` form.
- For A-share validation, use the resources prepared under `/Users/kumaai/Documents/Codex/workspace/投资纪要工作流/03 Resources`.
- If a local resource is stale or missing, refresh it before finalizing symbol annotations.

### 4. Write with strict structure

Always output the meeting note using `references/default_output_template.md` as the primary template and `references/output_format_guide.md` as rule constraints. The required baseline is: reader-facing meeting metadata first, speaker original text in actual speech order second, ambiguity section last. Reader-facing metadata must include `会议日期`, `整理时间`, `会议标题`, `会议类型`, and `会议系列`. Current preset/default meeting series is `研究所周会`, but the workflow must support newly added custom meeting series values and preserve the selected or added value through draft metadata, final Markdown, history filtering, archive metadata, and Dify knowledge-base sync. The final note is for human reading, not workflow debugging; do not include process-only fields such as `输入来源`, `整理说明`, tool names, logs, or draft-stage explanations.

### 4.1 Meeting-type skill dispatch

The base skill defines shared workflow, evidence handling, UTF-8, review, archive, and validation rules. It must not be used by Dify as a formatting shortcut for typed meeting notes.

When Dify invokes the Skill Agent, the meeting type selected in the import dropdown decides the actual skill package:
- `多人复盘会` -> `投资会议纪要-多人复盘会`
- `上市公司交流` -> `投资会议纪要-上市公司交流`
- `专家交流` -> `投资会议纪要-专家交流`
- `其他` or any custom meeting type -> `投资会议纪要-其他`

Hard rules:
- The selected type skill is the source of truth for output format differences. Dify may pass `meeting_type`, `custom_meeting_type`, `meeting_title`, `meeting_series`, custom meeting-series values, and input text, but Dify must not directly rewrite the output format after generation. `meeting_series` defaults to `研究所周会` when empty, and any newly added series value must be preserved as first-class metadata instead of being collapsed back to the default.
- Every type skill must read and obey this base skill for shared rules, then apply its own output-shape overrides.
- All typed outputs still keep the final ambiguity section `## 二、存疑与待确认`.
- `多人复盘会` keeps the current speaker + `【板块｜标的(代码)】` format.
- `上市公司交流` puts sector/target/code in the top title and metadata, then avoids repeating the same sector/target/code inside each speaker section.
- `专家交流` uses a Q&A form inside the main body: questions are bold; each answer starts directly with one bracketed topic tag such as `【需求变化】` or `【价格压力】`, followed by the answer content. Do not write `A:` or `A：` after the tag. The tag is not limited to one word, but it must accurately summarize the answer's main direction.
- `其他` keeps its own meeting type in metadata. Any Q&A content inside `其他`, `多人复盘会`, or `上市公司交流` must use the expert-call Q&A presentation for that local block: bold question, direct answer beginning with a bracketed topic tag, no `A:` / `A：`, and no artificial question numbering.

Non-negotiable rules:
- Use section titles exactly as `## 一、逐发言人原文整理` and `## 二、存疑与待确认`; do not append parenthetical labels such as `（人工格式）` or `（集中查看）`.
- In `## 一、逐发言人原文整理`, preserve the actual speech order exactly as it occurred. If a speaker appears multiple times, keep the later occurrence in its real position, using labels like `发言人3（后半段）` when helpful.
- The original-text section must be a polished corrected-original text, not a compressed analyst summary: remove only meaningless filler words, meaningless repeated words, and obvious ASR noise; fix punctuation and obvious ASR errors; keep every meaningful view, reason, number, timing, condition, catalyst, earnings expectation, position action, hesitation, and uncertainty. Do not summarize long speech blocks into 1-3 sentences; split them into multiple readable topic/symbol paragraphs instead.
- Keep the original speaker's perspective and pronouns in the original-text section. Do not rewrite first-person statements such as `我看好`, `我减仓`, or `我们明天对接` into third-person narration such as `某老师看好`, `其减仓`, or `团队将对接`.
- Do not rewrite speaker-original text in the organizer's own wording. Apart from punctuation, removing meaningless filler, correcting obvious ASR errors, and splitting topics, preserve the speaker's original wording, word order, judgment boundaries, and spoken style as much as possible. Do not polish it into research-report language.
- Segment by actual speech order first, then by speaker, then by sector/topic, then by symbol.
- If one speech block mentions multiple symbols, split it into multiple sub-sections.
- Within a speaker section, start each segment with a bracket tag like `【半导体｜中芯国际(688981.SH)】`. Do not repeat the speaker name inside the segment title.
- For uncertain words in the original-text section, keep the source wording and mark the doubtful fragment in bold markdown. In Word export, render these doubtful fragments as bold + underline so they are visibly marked.

### 5. Preserve the speaker's meaning

Allowed:
- Remove filler words and repeated verbal tics.
- Fix punctuation and obvious ASR noise.
- Split long paragraphs into readable units.
- Keep the speaker's original phrasing, sequence, and information density as much as practical.
- Keep the speaker's original wording and spoken style when the sentence is understandable.

Not allowed:
- Replace the speaker's meaning with your own analyst summary.
- Rewrite understandable original wording into the organizer's own language or research-report prose.
- Compress the meeting into an executive summary when the source contains more detailed original wording.
- Merge distinct views that were expressed separately.
- Omit hesitation, uncertainty, or conditional language that changes the intent.
- Omit catalyst nodes, timing, earnings numbers, or position-change details that appear in the source.
- Invent catalysts, estimates, or stock codes.

### 6. Review, then export to Obsidian (Markdown + Word only)

For Dify-generated notes:
- Treat both the initial transcript draft and the generated meeting-note draft as non-final.
- Send the transcript/extraction result to `scripts/meeting_minutes_review_server.py` through `/draft` with `stage=pre_agent`. The user edits this initial review draft first, marking different speakers, splitting paragraphs by natural topic or target, and directly correcting mistranscribed key terms, company names, stock codes, people, numbers, and finance terms. Confirming it must trigger the second Dify workflow run with `input_reviewed=true`; it must not export, sync, or archive the transcript draft.
- The second Dify run invokes the selected meeting-type skill and sends its cleaned Markdown to `/draft` with `stage=post_agent`. The user edits this second-review draft at `review_url` in the Word-style rich-text editor, confirming speaker names, targets, stock codes, key terms, numbers, and ambiguity marks are correct before archive confirmation. The page converts the edited content back to Markdown before saving or confirming so all downstream artifacts use the same source.
- Confirming the second-review draft creates the confirmed final draft and generates structured summary and target-table artifacts under the draft store. It then shows an archive-confirmation page.
- Only after the user clicks archive confirmation should the workflow export Markdown + Word, sync the final note to the Dify knowledge base, and trigger Google Drive sync.
- Never put an unreviewed initial transcript, unreviewed generated note, or final draft without archive confirmation into the final Obsidian directory, Google Drive, or the Dify knowledge base.

After the Markdown note is finalized, export it with:

```bash
python3 scripts/export_to_obsidian.py NOTE.md
```

Or use the shortcut:

```bash
scripts/save_to_my_obsidian.sh NOTE.md
```

Default export target:
- Vault folder: `/Users/kumaai/Documents/Codex/workspace/投资纪要工作流/01 Projects/会议纪要/YYYY-MM-DD/`
- Outputs: one same-name `.md` file and one same-name `.docx` file under the meeting-date folder. Do not generate PDF.
- After successful Markdown + Word export, update the whole Obsidian workflow folder to Google Drive with `scripts/sync_obsidian_to_gdrive.py`. In Dify, this is triggered by the human-confirmation action; raw uploaded files also trigger the same background sync immediately after `/archive-inputs` archives them.
- After export, keep only the latest Markdown+Word pair in `01 Projects/会议纪要`; move older meeting-note outputs to `04 Archive/测试用` if cleanup is requested.

The exporter should produce Markdown and Word outputs, then sync `/Users/kumaai/Documents/Codex/workspace/投资纪要工作流` to `gdrive:投资纪要工作流存档/投资纪要工作流`. The review server also writes the confirmed final note into the Dify `会议纪要整理知识库` dataset by calling `scripts/sync_minutes_to_dify_dataset.py`. If Word export fails, keep the Markdown file and report the missing dependency. If Dify knowledge sync or Google Drive sync fails, keep the local Markdown + Word outputs and report the failure without deleting local files.

## Resources

### scripts/archive_raw_inputs.py
Use to copy raw meeting files into `/Users/kumaai/Documents/Codex/workspace/投资纪要工作流/00 Inbox/会议原始记录/YYYY-MM-DD/YYYY-MM-DD - 会议标题/` before transcription or writing.

### scripts/organize_raw_archive_structure.py
Use to migrate or repair historical raw archives into the same date/meeting-session folder structure. Run it without `--apply` first to preview moves, then with `--apply --remove-empty-dirs` after checking the plan.

### scripts/process_transcript.py
Use for transcript cleanup, speaker-block detection, and candidate symbol extraction before final writing.

### scripts/query_symbol_candidates.py
Use to query local A-share, HK, US, and alias symbol resources. It returns ranked candidates, confidence, and a `confirmed` flag. Do not write an unconfirmed candidate into the note; keep it in the ambiguity section.

### scripts/export_dify_workflow_snapshot.py
Use after Dify graph changes or before risky workflow edits to export a reproducible local snapshot of the current Dify workflow graph. It writes redacted workflow metadata, graph/features JSON, node summaries, hashes, and `latest_snapshot.txt` under `/Users/kumaai/Documents/Codex/workspace/投资纪要工作流/03 Resources/dify-workflow-snapshots/`. Environment variables are not exported in plaintext.

### scripts/export_to_obsidian.py
Use to copy the finished Markdown into the meeting-note directory and generate a same-name Word file.

### scripts/sync_obsidian_to_gdrive.py
Use after export to update the full Obsidian workflow folder to Google Drive. It uses `rclone copy`, not destructive mirror sync, and excludes technical folders such as `.git`, `.transcribe-venv`, `__pycache__`, and `node_modules`.

### scripts/meeting_minutes_review_server.py
Use as the low-intrusion Dify review/history bridge. It exposes `/draft` to create a draft review page, `/review?id=...` for Word-style rich-text human editing and confirmation, `/confirm-input` to enter the skill run after initial review, `/confirm-archive` to write the final archive after second-review confirmation, `/history` for date/title/symbol/permission filtering, `/external-sources` for Obsidian-backed WeChat article/chat archives, `/target-query` for traceable target evidence search, `/sync-status` for Google Drive sync status, and `/health` for service checks. The review page keeps Markdown as the underlying saved source. Second-review confirmation generates post-review summary/table artifacts first; archive confirmation then calls `export_to_obsidian.py`, triggers Google Drive sync, and calls `sync_minutes_to_dify_dataset.py`.

### scripts/start_meeting_minutes_review_server.sh
Use to restart the review/history bridge in a detached `screen` session named `meeting_minutes_review`. This is the preferred local startup method because the review server must keep user-session access to the final Obsidian output folder under `Documents`.

### scripts/sync_minutes_to_dify_dataset.py
Use to create or update the human-confirmed note in the Dify `会议纪要整理知识库`. It reads local private config from `/Users/kumaai/Library/Application Support/kumaai-sync/dify-meeting-minutes.env`; do not hard-code API keys in notes, skills, or workflow docs. The Dify document mapping should live under `/Users/kumaai/Library/Application Support/kumaai-sync/meeting-minutes-review/`, not under the Obsidian vault.

### scripts/audit_dify_dataset_mapping.py
Use to audit whether local Obsidian final minutes and the Dify dataset document mapping are still aligned. It reports missing source files, wrong meeting dates, repeated document names, and document-name mismatches. Run it after backfill, after batch re-sync, or when historical search/knowledge-base results look duplicated.

### scripts/repair_dify_dataset_mapping.py
Use to prepare or apply non-destructive repairs for old Dify dataset mapping drift. It defaults to dry-run, only updates existing Dify documents by mapped `document_id`, skips missing local sources, and never deletes, archives, or chooses a document by duplicate name.

### scripts/check_investment_workflow_health.py
Use as the one-command local health check before or after Dify workflow changes, Docker reinstall, service restart, or sync troubleshooting. It checks Obsidian paths, Dify localhost pages, review/export/SenseVoice bridges, the WeChat external-source bridge, Dify Docker containers, Google Drive sync logs, Dify dataset mapping audit, and skill-copy drift across Codex, Dify Skill Agent, and the Obsidian skill archive. WorkBuddy has been removed from the maintained workflow and is no longer checked or synchronized.

### /Users/kumaai/新会议纪要工作流/scripts/wechat_tools_bridge.py
Use as the local bridge for the second-stage external-source pipeline. It exposes `/wechat-article/archive` and `/wechat-chat/analyze` on port 8770, archives raw WeChat materials by date, writes cleaned Markdown into the Obsidian workflow, and can sync the resulting knowledge document to a Dify dataset when the private dataset config is present. Start it with `/Users/kumaai/新会议纪要工作流/scripts/start_wechat_tools_bridge.sh`.

### scripts/validate_meeting_minutes_contract.py
Use to validate any generated or archived Markdown note against the current output contract. It requires meeting metadata plus `## 一、逐发言人原文整理` and `## 二、存疑与待确认`, and rejects old `AI结构化总结`, `标的汇总表`, extra third/fourth sections, and leaked tool logs.

### scripts/validate_word_export.py
Use to validate exported Word files. It opens the `.docx`, checks the current two-section contract, rejects old four-section content, verifies Chinese text is present, and can compare Markdown bold ambiguity terms against Word bold+underline runs.

### scripts/run_meeting_minutes_regression.py
Use after skill, Dify, prompt, or bridge changes to run the fixed text-only, audio-transcript-only, and audio+text regression samples under `references/regression_samples/`.

### scripts/run_dify_service_api_smoke.py
Use after Dify workflow graph or output-contract changes to run a real blocking Service API smoke test. It creates a temporary Dify app token, calls `/v1/workflows/run` with a small pre-reviewed Chinese transcript (`input_reviewed=true`), verifies `result_markdown`, `review_url`, `drafts_url`, `history_url`, `draft_id`, the current two-section contract, the direct editor, the draft list, and the history page, then deletes the temporary token. It does not click archive confirmation.

### scripts/organize_archive_by_date.py
Use to keep `/Users/kumaai/Documents/Codex/workspace/投资纪要工作流/04 Archive/测试用` organized by `YYYY-MM-DD` folders. `export_to_obsidian.py` runs it before Google Drive sync so archived meeting-note files do not remain loose in the archive root.

### scripts/sensevoice_transcription_server.py
Use as the local Dify bridge for audio uploads. It exposes a tiny HTTP endpoint that accepts multipart field `audio`, runs `scripts/transcribe_audio.py --engine sensevoice`, and returns JSON with `text`, `engine`, and `model`.

### scripts/transcribe_audio.py
Use to transcribe local audio when ASR tooling is available. It standardizes SenseVoice/FunASR transcription first, supports explicit `--engine fun-asr-nano` for Fun-ASR-Nano-2512 auxiliary comparison, and keeps Whisper fallback for missing dependencies or timestamp output formats.

### scripts/compare_asr_models.py
Use to create a short clip and compare SenseVoice against Fun-ASR-Nano-2512. It writes both transcripts, a unified diff, and a JSON report without changing the meeting-note archive.

### scripts/save_to_my_obsidian.sh
Use for the default personal export path without repeating long arguments.

### scripts/validate_utf8_text.py
Use to verify Markdown/TXT/CSV/JSON/TSV/SRT/VTT/YAML/log files and DOCX XML parts decode as UTF-8 and, with `--require-cjk`, still contain Chinese text. For skill package import checks, add `--portable-skill` so `SKILL.md` is rejected if it has a UTF-8 BOM, CRLF/CR line endings, invisible control characters, or anything before the opening frontmatter. Run it before export on the working Markdown and after export on the final `.md` + `.docx`.

### references/default_output_template.md
Use this as the default output template baseline (meeting metadata, original text, ambiguity section, processing notes).

### references/output_format_guide.md
Read before producing the final note. This reference defines the exact section order and formatting rules.

### references/word_export_style_reference.md
Read before exporting Word files. This reference captures the latest accepted DOCX format using `/Users/kumaai/Documents/Codex/workspace/投资纪要工作流/04 Archive/测试用/2026-04-27 - 投资会议纪要-舵主-标注版.docx` as the style example.

### references/proofreading_guide.md
Read when the transcript contains ASR mistakes, company-name ambiguity, or finance-term noise.

### references/symbol_sources.md
Read when validating stock codes or refreshing local symbol resources.

## Output Contract

Every final note must include:
- Meeting metadata
- Meeting series metadata (`会议系列`) for grouping and downstream processing. The current preset/default value is `研究所周会`; newly added series values are supported and must be preserved.
- Speaker original-text blocks in actual speech order
- Ambiguity section

For Dify, the final note is the human-confirmed version, not the model draft. The Dify workflow should return `review_url`, `history_url`, `draft_id`, and the draft Markdown; final local files and Dify knowledge-base documents are created only after review confirmation.

If the user asks for optimization later, preserve backward compatibility with this simplified structure unless they explicitly request a breaking change.
