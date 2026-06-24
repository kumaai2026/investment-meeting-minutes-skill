---
name: investment-meeting-minutes
description: "Use when Codex needs to turn a Chinese investment meeting recording, transcript, or mixed audio+text input into a strict Markdown meeting note with speaker segmentation, company-name correction, stock-symbol validation, source-file archiving, conditional Subagent review, target attribution, and Markdown/Word export. Triggers include: 整理会议录音, 整理投资会议纪要, 把这段转录整理成纪要, 输出 Obsidian 会议纪要, 校对公司名称和股票代码, 导出 md 和 word, 结合录音与文字整理, 按发言人/板块/标的分段, 多标的标题归因, 推荐标的识别, analysis ledger, subagent."
---

# Investment Meeting Minutes

## Overview

Produce a strict, repeatable investment meeting note for Chinese-language meetings. Archive all raw input files by date, keep the original wording as much as practical, remove only meaningless filler words and meaningless repeated words, split by speaker + sector + symbol, validate company names and stock codes, and export the human-confirmed Markdown + Word into the user's Obsidian workflow. When called from Dify, treat Dify as an adapter layer: read `references/dify_adapter_guide.md` for workflow fields, review gates, and sync behavior, but keep this base skill and the selected type skill as the output-format source of truth.

## Skill-first conditional Subagent positioning

This skill is Skill-first and contract-first with conditional Codex Subagents. It is not a full MAS framework. The selected type skill remains the final Markdown format authority; deterministic scripts own hard validation; Subagents only review and return findings.

Main Orchestrator is the only writer of final Markdown, Word, archive, and sync artifacts. Subagents must not modify final outputs.

Read these references when risk triggers appear:
- `references/subagent_workflow.md` for input flows, Subagent trigger conditions, fallback, and Dify boundary.
- `references/analysis_ledger_contract.md` before creating or validating `analysis_ledger.json` and `qa_report.json`.
- `references/target_attribution_policy.md` before splitting multi-target paragraphs or writing segment titles.
- `references/evidence_policy.md` before confirming names, codes, terms, customers, numbers, orders, capacity, or prices.
- `references/subagent_failure_policy.md` when spawn fails, times out, or returns invalid JSON.
- `references/sidecar_privacy_policy.md` before creating any internal artifact or downstream RAG-facing artifact.

Never write `analysis_ledger.json`, `qa_report.json`, reviewer JSON, role names, review URLs, draft IDs, paths, tool logs, or process-only fields into the final human-readable Markdown/Word note.

### Conditional Subagent orchestration

When Transcript Auditor conditions are met, explicitly spawn project-scoped `transcript_auditor`, wait for its structured result, merge the result into the internal `analysis_ledger`, then continue. Conditions:
- `audio_only`.
- `audio_plus_document` with conflicts.
- Speaker boundaries are unclear.
- Key entities, codes, numbers, units, or terms are low-confidence.
- Reliable time anchors are needed.

When pre-draft Content Reviewer conditions are met, explicitly spawn `content_integrity_reviewer` with `mode=pre_draft`, wait for its result, and let Main Orchestrator decide segmentation and headings. Conditions:
- One semantic segment contains more than one target.
- There is recommendation, buy, sell, add, reduce, avoid, or other investment action.
- Main discussion object and action object may differ.
- Customers, suppliers, competitors, comparable companies, upstream/downstream entities, or background entities appear.
- Orders, capacity, price, profit, revenue, gross margin, valuation, or other high-risk facts appear.
- Meeting type is `多人复盘会`.
- A previous version misidentified recommendation targets.

After the draft exists, formal meeting minutes should by default explicitly spawn `content_integrity_reviewer` with `mode=post_draft`, wait for findings, and let only Main Orchestrator revise the draft. Post-draft review may be skipped only for pure format conversion or when the user explicitly asks for a fast informal draft.

Do not spawn one Agent per paragraph. Use at most one Transcript Auditor thread and one Content Reviewer thread per meeting.

If spawn fails, do not pretend review passed. Low-risk tasks may fall back to single-agent processing; high-risk tasks must set `requires_human_review=true`; existing human confirmation gates remain mandatory; record failure in internal QA; do not write failure details into final note body.

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
- A meeting note may use only files uploaded, pasted, archived, extracted, or transcribed in the current meeting session. Do not search other date folders, old draft folders, historical archives, global upload caches, or "latest" transcript files to fill missing content. Historical notes and external sources are allowed only for name/code/term verification, never as meeting-content source text.
- Archived raw files must use the standard filename pattern `YYYY-MM-DD - 会议标题 - 原始NN-材料类型.扩展名`, for example `2026-05-13 - AI数据中心温控企业海外拓展与市场策略交流 - 原始01-文稿.docx` and `2026-05-13 - AI数据中心温控企业海外拓展与市场策略交流 - 原始02-录音.mp3`. Material types should use `文稿`, `录音`, `录像`, or `附件`. If the title is not passed explicitly, `archive_raw_inputs.py` should infer it from the first non-empty DOCX paragraph or first TXT/MD line when possible; only fall back to a cleaned source filename when no title can be inferred. Do not keep generic WeChat or export names such as `export_*.mp3` as the final archive filename when a title is known or inferable.
- If filenames collide, preserve both files by adding a timestamp or numeric suffix.
- Do not expose raw-file archive details in the final note body. Store source-file details in draft metadata and logs; the final human-readable note should not include process fields such as `输入来源` or `整理说明`.
- Read `references/archive_naming_contract.md` when changing archive/export naming, Dify archive bridges, or any code that writes files into the workflow archive.

Use `scripts/archive_raw_inputs.py` when raw files are available.

Example:

```bash
python3 scripts/archive_raw_inputs.py INPUT.docx INPUT.mp3 --date 2026-04-28 --title "会议标题"
```

Handle these cases:
- `audio_only`: transcribe first, then run conditional Transcript Auditor when required. Low-confidence words, speaker-boundary issues, timestamps, and suspected codes are recorded in `analysis_ledger`.
- `document_only`: skip audio transcription, run conditional pre-draft Content Reviewer when multi-target or high-risk claims appear, and do not output timestamps anywhere in the final meeting note body.
- `audio_plus_document`: use both sources as evidence. The document must not automatically override audio, and audio must not automatically override the document. Put conflicts into `analysis_ledger.transcript_audit` instead of forcing a merge.
- Dify calls: read `references/dify_adapter_guide.md`. If `input_reviewed` is missing or false, do not run meeting-note formatting. Dify may pass already-extracted or transcribed text fields; do not ask for the same materials again.

When audio is provided:
- First use plain SenseVoice through the local FunASR runtime as the primary transcript and timestamp source. Do not enable `spk_model=cam++`, `fsmn-vad`, or other VAD/speaker-separation paths in the default pre-agent transcription path. VAD and speaker diarization are currently disabled for the maintained default workflow.
- Keep Fun-ASR-Nano-2512 as an explicit auxiliary proofreading option for cross-checking finance terms, company names, stock codes, numbers, and English abbreviations. Do not run it by default, and do not replace the primary SenseVoice transcript automatically only because Nano differs; surface conflicts for human review.
- Use `scripts/transcribe_audio.py` as the standard entry point. Its default `--engine auto` only uses plain SenseVoice through FunASR; if SenseVoice/FunASR is unavailable, fail clearly and continue only with user-provided text or an existing transcript. Do not downgrade, fall back, or explicitly switch to Whisper/other ASR for audio transcription. Use `--engine fun-asr-nano --nano-hub ms --nano-model FunAudioLLM/Fun-ASR-Nano-2512` only for auxiliary comparison runs.
- Keep Nano runtime isolated when possible. The local deployment may set `FUNASR_NANO_PYTHON` to a Nano-specific virtualenv and `FUNASR_MODEL_CACHE` to a local model cache; do not vendor model weights or virtualenv contents into a reusable GitHub skill package.
- Default SenseVoice model: `iic/SenseVoiceSmall`; default auxiliary model: `FunAudioLLM/Fun-ASR-Nano-2512`; default language: `zh` for SenseVoice and `中文` for Nano; default output: `.txt`.
- If the user needs time anchors, use SenseVoice/FunASR `--output-format json` or `--output-format all`. Do not call Whisper/other ASR to generate `vtt`/`srt`/`tsv`.
- If local ASR is unavailable, tell the user clearly what is missing and continue with any provided text instead of blocking the whole workflow.
- Before production-like audio or Dify use, read `references/runtime_readiness_guide.md` and run `scripts/check_investment_workflow_health.py --strict`. Runtime jobs must not download models or install dependencies.

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
- `references/target_attribution_policy.md`
- `references/evidence_policy.md`

Correction rules:
- Correct company names, sectors, people, and finance terminology from context.
- Validate symbols before writing them into the final note.
- For every paragraph, identify the primary target and all mentioned targets before writing the title. If the source contains recommendation, watch-list, buy/sell/add/reduce, bullish/bearish, or key tracking language, identify the recommendation target separately from background, comparison, customer, supplier, competitor, upstream/downstream, and incidental mentions.
- Segment titles must cover the true primary target and recommendation target. Do not treat the first-mentioned target, most frequent target, customer, supplier, competitor, or comparison target as the recommendation target unless the source explicitly supports it.
- For target names, stock codes, sectors, and A-share financial knowledge, call the `a-stock-data` capability when available and use its live/network data sources first. At minimum, use live quote/company-info style checks such as Tencent quote, Eastmoney stock info/news, exchange/company disclosures, or CNINFO announcements to confirm the candidate name/code is currently valid. `scripts/query_symbol_candidates.py` and local symbol CSVs are only candidate generators or fallback aids; they are not sufficient evidence by themselves when internet access is available.
- For any doubtful content, do not rely on a single evidence path. Cross-check the source audio/transcript, the surrounding meeting context, `a-stock-data` target evidence, and professional term search before deciding whether to correct the text or keep it as ambiguous.
- For every non-person doubtful content item, internet/professional-source search is mandatory. This applies even when local symbol lookup returns a plausible candidate. Search reliable professional sources and compare candidates against meeting context; prefer `a-stock-data` live sources, official disclosures, company websites, exchange filings, CNINFO, industry reports, regulator/association pages, and reputable financial/news sources over generic search snippets. If search evidence conflicts with the audio or context, keep the original wording, mark the doubtful fragment inline, and add a row in `## 二、存疑与待确认` explaining the competing interpretations.
- Pure person-name or speaker-name uncertainty may be ignored unless the identity changes an investment fact, target mapping, role attribution, or source credibility. Do not create `## 二、存疑与待确认` rows just to confirm ordinary names, nicknames, or speaker labels.
- Search strategy for ASR/noisy terms: do not only search the raw uncertain phrase. First generate a candidate set using homophones, near-homophones, common ASR substitutions, similar characters, pinyin initials, finance abbreviations, sector vocabulary, nearby companies already mentioned, and contextual anchors such as products, customers, catalysts, dates, or numbers. Query local symbol candidates for every plausible company candidate, then verify the narrowed candidates with live/network sources. For example, a raw fragment like `盛新材` must also test candidates such as `禾盛新材`; `印东微` must test near-homophones such as `燕东微`; `盛静科技` must test `盛剑科技` when the sector context fits.
- Forced ambiguity verification: when real non-person doubtful content exists, create `## 二、存疑与待确认`. Every real row must be checked against the surrounding meeting context and at least one live/search evidence path such as `a-stock-data` network data, company disclosures, official websites, exchange filings, CNINFO, industry reports, or reliable financial/news sources. Local symbol resources may be cited as candidate-generation evidence but must not be the only evidence unless internet access is unavailable. Do not leave a row as a bare "待确认" item. The `核验依据` cell must explicitly include both `上下文：...` and `检索/证据：...`; if either part cannot be completed, state what was searched and why it remains unresolved. If there is no doubtful content, do not generate `## 二、存疑与待确认`.
- Prefer Chinese investment context when choosing between multiple listings.
- Use A-share first for typical mainland research context, then Hong Kong, then US, unless the source explicitly points elsewhere.
- If you cannot confirm a name or code, mark it in the ambiguity section instead of guessing.
- For uncertain proper nouns in source text, actively verify against available resources (local symbol resources, company disclosures, or reliable web sources) before finalizing.
- Use `scripts/query_symbol_candidates.py` for local candidate lookup before writing a stock code, but treat it as a prefilter. Only write a code when the candidate is locally plausible and live/network evidence confirms the same name/code or official listing. If local lookup is `ambiguous` or `not_found`, expand candidates using the search strategy above before deciding; if still unresolved, keep the source wording and add it to `## 二、存疑与待确认`.
- If `## 二、存疑与待确认` exists, the table header is always `时间戳 | 原始表述 | 当前判断 | 存疑原因 | 候选项 | 核验依据 | 人工确认`.
- Use the timestamp from the transcript/audio segment when available, preferably in `HH:MM:SS` or `MM:SS` form. If the current source is text/Word/PDF-only or no reliable time anchor exists, write `未提供` in the table timestamp cell.
- Do not estimate timestamps from the relative position of the cleaned meeting note or summary text, because edited prose length and speaking duration drift too much.
- For audio/video or timestamped transcript sources, every uncertain fragment that appears in the original-text body must carry its ambiguity timestamp inline, immediately after the bold doubtful fragment, using `**存疑词**（存疑时间戳：HH:MM:SS）`. For text/Word/PDF-only sources, mark only `**存疑词**` inline and put `未提供` in the ambiguity table timestamp cell.
- Fill `核验依据` with both context and search/evidence notes. Leave the `人工确认` cells empty.

Symbol-source rules:
- The GitHub repo `LondonMarket/Global-Stock-Symbols` is useful for US/HK/global coverage, but it does not cover mainland A-share tickers in the expected `.SH` / `.SZ` / `.BJ` form.
- For A-share validation, use the resources prepared under `/Users/kumaai/Documents/Codex/workspace/投资纪要工作流/03 Resources`.
- If a local resource is stale or missing, refresh it before finalizing symbol annotations.

### 4. Write with strict structure

Always output the meeting note using `references/default_output_template.md` as the primary template and `references/output_format_guide.md` as rule constraints. The required baseline is: reader-facing meeting metadata first, speaker original text in actual speech order second, and the ambiguity section only when real doubtful content exists. Reader-facing metadata must include `会议日期`, `整理时间`, `会议标题`, `会议类型`, and `会议系列`. Current preset/default meeting series is `研究所周会`, but the workflow must support newly added custom meeting series values and preserve the selected or added value through draft metadata, final Markdown, history filtering, archive metadata, and Dify knowledge-base sync. The final note is for human reading, not workflow debugging; do not include process-only fields such as `输入来源`, `整理说明`, tool names, logs, or draft-stage explanations.

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
- Type skills may use `analysis_ledger` as internal guidance. It does not override the selected type skill, and it must not be copied into the final note body.
- Typed outputs include the final ambiguity section `## 二、存疑与待确认` only when real doubtful content exists.
- When the ambiguity section exists, the table schema is always `时间戳 | 原始表述 | 当前判断 | 存疑原因 | 候选项 | 核验依据 | 人工确认`. `核验依据` must include both context judgment and search/evidence verification. Leave `人工确认` cells empty for the user.
- `多人复盘会` keeps the current speaker + `【板块｜标的(代码)】` format.
- `上市公司交流` puts sector/target/code in the top title and metadata, then avoids repeating the same sector/target/code inside each speaker section.
- `专家交流` uses a Q&A form inside the main body: questions are bold; each answer starts directly with one bracketed topic tag such as `【需求变化】` or `【价格压力】`, followed by the answer content. Do not write `A:` or `A：` after the tag. The tag is not limited to one word, but it must accurately summarize the answer's main direction.
- `其他` keeps its own meeting type in metadata. Any Q&A content inside `其他`, `多人复盘会`, or `上市公司交流` must use the expert-call Q&A presentation for that local block: bold question, direct answer beginning with a bracketed topic tag, no `A:` / `A：`, and no artificial question numbering.

Non-negotiable rules:
- Use section title `## 一、逐发言人原文整理` exactly. When real doubtful content exists, use section title `## 二、存疑与待确认` exactly; do not append parenthetical labels such as `（人工格式）` or `（集中查看）`.
- In `## 一、逐发言人原文整理`, preserve the actual speech order exactly as it occurred. If a speaker appears multiple times, keep the later occurrence in its real position, using labels like `发言人3（后半段）` when helpful.
- The original-text section must be a polished corrected-original text, not a compressed analyst summary: remove only meaningless filler words, meaningless repeated words, and obvious ASR noise; fix punctuation and obvious ASR errors; keep every meaningful view, reason, number, timing, condition, catalyst, earnings expectation, position action, hesitation, and uncertainty. Do not summarize long speech blocks into 1-3 sentences; split them into multiple readable topic/symbol paragraphs instead.
- Keep the original speaker's perspective and pronouns in the original-text section. Do not rewrite first-person statements such as `我看好`, `我减仓`, or `我们明天对接` into third-person narration such as `某老师看好`, `其减仓`, or `团队将对接`.
- Do not rewrite speaker-original text in the organizer's own wording. Apart from punctuation, removing meaningless filler, correcting obvious ASR errors, and splitting topics, preserve the speaker's original wording, word order, judgment boundaries, and spoken style as much as possible. Do not polish it into research-report language.
- Segment by actual speech order first, then by speaker, then by sector/topic, then by symbol.
- If one speech block mentions multiple symbols, split it into multiple sub-sections.
- If one speech block includes a primary target and a different recommendation target, either split the block or include both in the segment title. Do not omit the recommendation target.
- Distinguish target roles before finalizing a title: primary, recommendation, comparison, customer, supplier, competitor, upstream, downstream, industry background, incidental, and uncertain.
- Within a speaker section, start each segment with a bracket tag like `【半导体｜中芯国际(688981.SH)】`. Do not repeat the speaker name inside the segment title.
- For uncertain words in the original-text section, keep the source wording and mark the doubtful fragment in bold markdown. When audio/video or timestamped transcript exists, immediately after each bold doubtful fragment include the inline ambiguity timestamp in the form `（存疑时间戳：HH:MM:SS）`; use ASR sentence/word timestamps first and VAD/audio-segment anchors as the fallback, and never derive timestamps by proportional alignment against the cleaned note text. When the session is text/Word/PDF-only, mark only the bold doubtful fragment and do not add any timestamp placeholder. In Word export, render these doubtful fragments as bold + underline so they are visibly marked.

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

For Dify-generated notes, follow `references/dify_adapter_guide.md`: initial transcript drafts and generated meeting-note drafts are non-final, the type skill may run only after human initial review, and final archive/sync may run only after archive confirmation. Never put an unreviewed transcript, unreviewed generated note, or final draft without archive confirmation into the final Obsidian directory, Google Drive, or the Dify knowledge base.

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
- Outputs: one same-name `.md` file and one same-name `.docx` file under the meeting-date folder. Preferred final filename pattern is `YYYY-MM-DD - 会议标题 - 会议类型.md` and `YYYY-MM-DD - 会议标题 - 会议类型.docx`. Do not generate PDF.
- After successful Markdown + Word export, update the whole Obsidian workflow folder to Google Drive with `scripts/sync_obsidian_to_gdrive.py`. In Dify, this is triggered by the human-confirmation action; raw uploaded files also trigger the same background sync immediately after `/archive-inputs` archives them.
- After export, keep only the latest Markdown+Word pair in `01 Projects/会议纪要`; move older meeting-note outputs to `04 Archive/测试用` if cleanup is requested.

The exporter should produce Markdown and Word outputs, then sync `/Users/kumaai/Documents/Codex/workspace/投资纪要工作流` to `gdrive:投资纪要工作流存档/投资纪要工作流`. The review server also writes the confirmed final note into the Dify `会议纪要整理知识库` dataset by calling `scripts/sync_minutes_to_dify_dataset.py`. If Word export fails, keep the Markdown file and report the missing dependency. If Dify knowledge sync or Google Drive sync fails, keep the local Markdown + Word outputs and report the failure without deleting local files.

## Resources

### scripts/archive_raw_inputs.py
Use to copy raw meeting files into `/Users/kumaai/Documents/Codex/workspace/投资纪要工作流/00 Inbox/会议原始记录/YYYY-MM-DD/YYYY-MM-DD - 会议标题/` before transcription or writing. Use `--dry-run --json` in automation to preview deterministic target paths before copying.

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
Use as the one-command local health check before or after Dify workflow changes, Docker reinstall, service restart, or sync troubleshooting. Use `--strict` before production-like audio/Dify jobs to fail on missing Python dependencies or incomplete local ASR model caches instead of discovering them during a meeting run. It also checks Obsidian paths, Dify localhost pages, review/export/SenseVoice bridges, the WeChat external-source bridge, Dify Docker containers, Google Drive sync logs, Dify dataset mapping audit, and skill-copy drift across Codex, Dify Skill Agent, and the Obsidian skill archive. WorkBuddy has been removed from the maintained workflow and is no longer checked or synchronized.

### /Users/kumaai/新会议纪要工作流/scripts/wechat_tools_bridge.py
Use as the local bridge for the second-stage external-source pipeline. It exposes `/wechat-article/archive` and `/wechat-chat/analyze` on port 8770, archives raw WeChat materials by date, writes cleaned Markdown into the Obsidian workflow, and can sync the resulting knowledge document to a Dify dataset when the private dataset config is present. Start it with `/Users/kumaai/新会议纪要工作流/scripts/start_wechat_tools_bridge.sh`.

### scripts/validate_meeting_minutes_contract.py
Use to validate any generated or archived Markdown note against the current output contract. It requires meeting metadata plus `## 一、逐发言人原文整理` and `## 二、存疑与待确认`, and rejects old `AI结构化总结`, `标的汇总表`, extra third/fourth sections, and leaked tool logs.

### scripts/validate_word_export.py
Use to validate exported Word files. It opens the `.docx`, checks the current output contract, rejects old four-section content, verifies Chinese text is present, and can compare Markdown bold ambiguity terms against Word bold+underline runs.

### scripts/validate_analysis_ledger.py
Use to validate `analysis_ledger.json` and optional `qa_report.json`. It checks artifact version, enums, duplicate IDs, ID references, recommendation evidence, unresolved human-review flags, post-draft severity, QA GO/NO-GO consistency, and recursive privacy leaks.

### scripts/validate_title_target_consistency.py
Use to validate that final Markdown headings are consistent with `analysis_ledger.json`. It reuses `validate_meeting_minutes_contract.py`, checks heading target coverage, recommendation target inclusion, customer/supplier/comparison false heading promotion, unconfirmed ticker leakage, and internal field leakage.

### scripts/score_target_attribution.py
Use to compare reviewer output with human gold labels. It reports primary and recommendation precision/recall, role false positives, customer/supplier/comparison recommendation false positives, heading coverage, and action accuracy.

### scripts/run_meeting_minutes_regression.py
Use after skill, Dify, prompt, or bridge changes to run the fixed text-only, audio-transcript-only, and audio+text regression samples under `references/regression_samples/`.

### scripts/run_dify_service_api_smoke.py
Use after Dify workflow graph or output-contract changes to run a real blocking Service API smoke test. It creates a temporary Dify app token, calls `/v1/workflows/run` with a small pre-reviewed Chinese transcript (`input_reviewed=true`), verifies `result_markdown`, `review_url`, `drafts_url`, `history_url`, `draft_id`, the current output contract, the direct editor, the draft list, and the history page, then deletes the temporary token. It does not click archive confirmation.

### scripts/organize_archive_by_date.py
Use to keep `/Users/kumaai/Documents/Codex/workspace/投资纪要工作流/04 Archive/测试用` organized by `YYYY-MM-DD` folders. `export_to_obsidian.py` runs it before Google Drive sync so archived meeting-note files do not remain loose in the archive root.

### scripts/sensevoice_transcription_server.py
Use as the local Dify bridge for audio uploads. It exposes a tiny HTTP endpoint that accepts multipart field `audio`, runs `scripts/transcribe_audio.py --engine sensevoice`, and returns JSON with `text`, `engine`, and `model`.

### scripts/start_sensevoice_transcription_server.sh
Use to start the local SenseVoice/FunASR transcription bridge with stable local cache environment variables. It sets `FUNASR_MODEL_CACHE`, `MODELSCOPE_CACHE`, `HF_HOME`, `FUNASR_NANO_PYTHON`, UTF-8 settings, and PATH before running `sensevoice_transcription_server.py`. The macOS LaunchAgent template under `launchagents/com.kumaai.sensevoice-transcription-server.plist` uses this script so Dify can call `http://host.docker.internal:8765/transcribe` without triggering model downloads on each meeting.

### scripts/transcribe_audio.py
Use to transcribe local audio when ASR tooling is available. It standardizes SenseVoice/FunASR transcription, supports explicit `--engine fun-asr-nano` for Fun-ASR-Nano-2512 auxiliary comparison, and must not downgrade to Whisper or other ASR when dependencies or timestamp formats are missing.

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

### references/archive_naming_contract.md
Read before changing raw-file archive naming, final-note export naming, Dify archive bridges, or any code that writes files into the meeting workflow archive.

### references/dify_adapter_guide.md
Read only for Dify/Skill Agent integration work. It defines Dify fields, review gates, type-skill dispatch, returned URLs/IDs, and archive/sync boundaries. Keep Dify adapter details out of the human-readable final note.

### references/runtime_readiness_guide.md
Read before production-like audio transcription, Dify smoke tests, or deployment migration. It defines the no-runtime-download rule and the strict readiness check.

### references/word_export_style_reference.md
Read before exporting Word files. This reference captures the latest accepted DOCX format using `/Users/kumaai/Documents/Codex/workspace/投资纪要工作流/04 Archive/测试用/2026-04-27 - 投资会议纪要-舵主-标注版.docx` as the style example.

### references/proofreading_guide.md
Read when the transcript contains ASR mistakes, company-name ambiguity, or finance-term noise.

### references/symbol_sources.md
Read when validating stock codes or refreshing local symbol resources.

### references/subagent_workflow.md
Read when the source is `audio_only`, `audio_plus_document`, multi-target, or otherwise high risk. It defines the conditional Subagent flow, fallback, human gates, and Dify boundary.

### references/analysis_ledger_contract.md
Read before creating or validating `analysis_ledger.json` or `qa_report.json`.

### references/target_attribution_policy.md
Read before segmenting multi-target paragraphs or writing titles that may involve recommendation, comparison, customer, supplier, competitor, or background targets.

### references/evidence_policy.md
Read before confirming company names, stock codes, terms, customers, numbers, orders, capacity, prices, revenue, profit, margin, or valuation claims.

### references/subagent_failure_policy.md
Read when custom agent spawn or reviewer output fails.

### references/sidecar_privacy_policy.md
Read before creating internal artifacts or downstream ingestion artifacts.

## Output Contract

Every final note must include:
- Meeting metadata
- Meeting series metadata (`会议系列`) for grouping and downstream processing. The current preset/default value is `研究所周会`; newly added series values are supported and must be preserved.
- Speaker original-text blocks in actual speech order
- Ambiguity section only when real doubtful content exists

For Dify, the final note is the human-confirmed version, not the model draft. The Dify workflow should return `review_url`, `history_url`, `draft_id`, and the draft Markdown; final local files and Dify knowledge-base documents are created only after review confirmation.

If the user asks for optimization later, preserve backward compatibility with this simplified structure unless they explicitly request a breaking change.
