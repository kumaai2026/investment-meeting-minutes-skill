---
name: investment-meeting-minutes
description: "Use when Codex needs to turn a Chinese investment meeting recording, transcript, or mixed audio+text input into a strict Markdown meeting note with speaker segmentation, company-name correction, stock-symbol validation, source-file archiving, Subagent-assisted intermediate drafts and omission checks, and Markdown/Word export. Triggers include: 整理会议录音, 整理投资会议纪要, 把这段转录整理成纪要, 输出 Obsidian 会议纪要, 校对公司名称和股票代码, 导出 md 和 word, 结合录音与文字整理, 按发言人/版块分段."
---

# Investment Meeting Minutes

## Overview

Produce a strict Chinese investment meeting note from the current meeting's audio, transcript, document, or mixed materials. Preserve the speaker's meaning, validate names and stock codes before writing confirmed entities, and export the human-confirmed Markdown + Word note.

Use the fastest safe path for the source risk. The default path is a single final writer with deterministic checks; enable Subagents only when the source is long, noisy, conflict-heavy, multi-target, or fact-sensitive. Write final Markdown, Word, archive outputs, and sync payloads only through the main workflow.

For Dify workflow integration, read `references/dify_adapter_guide.md`.

## Stable Contract

- Workflow after input archive: 转录 -> 校对 -> 识别 -> 编辑 -> 排版.
- Source boundary: use only current-session materials as meeting-content sources. External sources may verify names, codes, terms, or public facts, but must not add meeting content.
- ASR: use local SenseVoiceSmall as the primary transcript model and FunASR `fa-zh` / timestamp predictor only to align the SenseVoice chunk text into a sentence-level timestamp index. Do not switch to Whisper or another ASR. If the local ASR/timestamp chain cannot run, continue only with provided text or an existing transcript.
- Final writer: Subagents may produce intermediate notes, candidate blocks, verification notes, and omission findings; they must not directly write final deliverables.
- Run profile: prefer `fast_document` for short, clean document-only sources; use `standard` for ordinary meetings; use `strict_audio_or_dify` for long audio, audio/document conflicts, production-like Dify runs, or high-risk facts.
- Meeting type: default to `多人复盘会`. Use `上市公司交流` only for a single-company special meeting. Use `专家交流` only for expert Q&A. Do not create `其他`.
- Output format: follow `references/output_contract.md` for final structure, segmentation, heading format, meeting-type differences, ambiguity-table columns, and Word style.
- Doubtful items: non-person doubtful content must run the stable verification prompt in `references/verification_policy.md`.
- Validators: keep validation to encoding, Markdown/Word structure, and regression samples. Do not add content-direction validators or Subagent-output validators.

## Workflow

### Choose run profile

- `fast_document`: use for short, clean document-only material with clear speakers and few/no uncertain entities. Skip Subagents and ASR readiness checks. Run local formatting validators before export.
- `standard`: use for ordinary document-only or audio-plus-document work. Batch local entity/code candidate lookup first; use Subagents only for triggered risk areas.
- `strict_audio_or_dify`: use for audio-only, long/noisy meetings, audio/document conflicts, high-risk facts, production-like imports, or Dify workflows. Run the relevant readiness profile before the expensive step.

### Select meeting type

Choose the meeting type from evidence, not only from the number of speakers.

- If the user or reviewed input explicitly sets `会议类型`, use it unless the materials clearly contradict it.
- Use `上市公司交流` when the meeting is centered on one listed company or one intended listing target, and the discussion mainly covers that company's business, products, customers, revenue, margin, capacity, orders, management answers, capital actions, or risk. This remains `上市公司交流` even if there are multiple speakers or investor questions.
- Use `专家交流` when the main speaker is an external expert, channel participant, industry practitioner, consultant, doctor, dealer, supply-chain participant, or other non-company-management source answering questions based on industry experience, channel checks, or third-party observations. The subject can be one company or one industry.
- Use `多人复盘会` for morning meetings, weekly meetings, market reviews, portfolio reviews, and multi-speaker investment sharing where different speakers discuss different targets, sectors, positions, trading actions, or market rhythm.
- If evidence is insufficient or conflicting, keep the default `多人复盘会` and do not invent another category.

### 0. Prepare Inputs

Archive raw files before transcription or writing. Use `scripts/archive_raw_inputs.py`; read `references/archive_naming_contract.md` before changing archive/export naming or archive bridges.

Handle source modes:
- `audio_only`: archive, then transcribe with SenseVoice.
- `document_only`: archive, then organize from the provided text/document.
- `audio_plus_document`: archive both; use both as evidence and keep conflicts visible.

Keep Chinese text files and generated Markdown/TXT/JSON/YAML as UTF-8 without BOM. In Python text I/O, pass `encoding="utf-8"`. If UTF-8 decoding fails or replacement characters appear, stop and report the affected file.

### 1. 转录

When audio is provided, use `scripts/transcribe_audio.py` for local SenseVoiceSmall primary transcription, Paraformer-Large auxiliary cross-checking, and timestamp-index preparation.

Default audio pipeline:
1. Run SenseVoiceSmall through local FunASR as the primary ASR transcript.
2. Keep 60-second audio chunks, chunk paths, and the SenseVoice text for each chunk.
3. Run Paraformer-Large on the same chunks as an auxiliary ASR cross-check for finance terms, company names, stock codes, numbers, and English abbreviations.
4. Do not automatically replace the SenseVoiceSmall transcript with Paraformer-Large output. Use Paraformer differences as proofreading evidence, and surface unresolved conflicts in `transcript_audit` or `suspect_confirmation`.
5. Build a near-verbatim `aligned_transcript` from the SenseVoice primary transcript plus confirmed cross-check corrections. Do not use cleaned meeting-note prose for timestamp alignment.
6. Run FunASR/fa-zh timestamp forced alignment on each chunk audio + matching `aligned_transcript` or SenseVoice chunk text to build `timestamp_index.json`.
7. Use the timestamp index as the authoritative timestamp source for ambiguity rows.

Timestamp-index rules:
- Do not use Whisper for transcription, fallback transcription, cross-checking, or timestamp generation.
- Do not re-transcribe the full audio only to create timestamps. Paraformer-Large may be used for auxiliary text cross-checking, but the timestamp chain should forced-align the primary or corrected near-verbatim chunk text against its matching audio chunk.
- Do not run forced alignment over a full long recording in one pass. Align by 60-second chunks or shorter VAD segments.
- `timestamp_index.json` entries must include `start`, `end`, `start_ms`, `end_ms`, `chunk_index`, `text`, `source`, and `precision`.
- `source` should distinguish `sensevoice`, `sensevoice_paraformer_checked`, `fa_zh_forced_alignment`, and fallback segment sources when applicable.
- `precision` should distinguish `sentence`, `phrase`, `segment`, `chunk`, and `unavailable`.
- For ambiguity rows, first match the doubtful term to the timestamp index and output `HH:MM:SS-HH:MM:SS`. If no sentence/phrase match is available, fall back to the VAD or chunk range and mark it as `片段级`.
- Model downloads, dependency installation, and first-cache warmup are setup work, not formal transcription time.
- Before production-like audio, read `references/runtime_readiness_guide.md` and run `scripts/check_investment_workflow_health.py --profile asr --strict` if that profile is implemented. If not implemented, use the existing strict health check or `scripts/transcribe_audio.py --check-model-cache`. Use full health checks only for production-like Dify or end-to-end runtime validation.

### 2. 校对

Use `scripts/process_transcript.py` when text is long, noisy, or missing clear speaker boundaries. Correct obvious ASR noise while preserving the speaker's viewpoint, order, uncertainty, and meaningful wording.

Use the Transcript Auditor Subagent when audio is long, noisy, multi-speaker, has unclear speaker boundaries, or has audio/document conflicts.

### 3. Correct names and symbols

Use references only when they match the uncertainty:
- `references/verification_policy.md`: ASR cleanup, speaker naming, company names, stock-code lookup, evidence boundaries, stable doubtful-item prompt, target roles, investment actions, and heading coverage.

Rules:
- Start from meeting context before choosing a company, ticker, term, customer, supplier, number, date, or event.
- Confirm company names and stock codes before writing them as facts, following `references/verification_policy.md`. Local candidates and ASR output are clues, not proof.
- Batch local candidate lookup before live verification when several names appear, for example `scripts/query_symbol_candidates.py --batch-file terms.txt --json`. Use `a-stock-data` live sources when available; use `scripts/query_symbol_candidates.py` only as a candidate generator.
- If a non-person item cannot be confirmed, keep the source wording, mark the doubtful fragment, and put it in `## 二、存疑与待确认`.
- For audio/video or timestamped transcript sources, locate each doubtful fragment against `timestamp_index.json` before writing `## 二、存疑与待确认`. Use `HH:MM:SS-HH:MM:SS` when the fragment matches a timestamped sentence or phrase. If only the chunk is known, fall back to the chunk range such as `00:03:00-00:04:00` and mark the basis as `片段级` in `核验依据` or the internal working field. If the source is text/document-only or no reliable audio anchor exists, write `未提供`.
- Do not estimate ambiguity timestamps from the relative position of cleaned notes, summaries, or edited paragraphs.
- Ignore pure person-name uncertainty unless it changes an investment fact or attribution.

Use the Content Integrity Reviewer Subagent when target attribution, multi-target headings, high-risk facts, doubtful-item verification, or omission checks would materially reduce errors.

### 4. 编辑

Write one unified draft. Use `references/output_contract.md`.

Use a source-faithful editing pass:
- Preserve actual speech order and speaker perspective. If a speaker appears multiple times, keep later turns in their real position.
- Remove only filler words, meaningless repetition, stutters, and obvious ASR noise. Keep judgments, reasons, numbers, time points, catalysts, business terms, uncertainty, and conditions.
- Fix confirmed ASR errors in names, tickers, product terms, English abbreviations, and numbers, but do not rewrite the speaker's logic into research-report prose.
- Split long speech into readable paragraphs at natural pauses, topic shifts, slide/page changes, or Q&A turns. Do not create thematic summaries that were not present in the source.
- For `上市公司交流`, put the main company and code in the meeting title, for example `广立微(301095.SZ)交流会`. Do not repeat the same main target line under every paragraph; add a `标的：` line only when a paragraph introduces other listed targets or when attribution would otherwise be unclear.
- Do not include workflow debugging fields such as `输入来源`, `整理说明`, tool names, logs, paths, review URLs, draft IDs, or draft-stage explanations.

### 5. 排版

After final Markdown confirmation, validate and export. For temporary quality checks or before archive confirmation, use exporter dry/local options such as `--no-sync` when available; for final confirmed delivery, keep the default Markdown + Word export and background sync behavior.

```bash
python3 scripts/validate_utf8_text.py NOTE.md --require-cjk
python3 scripts/validate_meeting_minutes_contract.py NOTE.md --json
python3 scripts/export_to_obsidian.py NOTE.md
```

The exporter writes one Markdown file and one Word file. Do not generate PDF. If Word export, knowledge-base sync, or Google Drive sync fails, keep local outputs and report the failure without deleting files.

## Reference Routing

- Dify integration: `references/dify_adapter_guide.md`.
- Output structure, meeting-type formatting, ambiguity tables, and Word style: `references/output_contract.md`.
- Archive/export naming: `references/archive_naming_contract.md`.
- Runtime readiness: `references/runtime_readiness_guide.md`.
- Name/code/entity proofreading, evidence boundaries, target attribution, and doubtful-item verification prompt: `references/verification_policy.md`.
- Subagent workflow and failure handling: `references/subagent_guide.md`.

## Resources

Core scripts:
- `archive_raw_inputs.py`: copy current raw files into the workflow archive.
- `transcribe_audio.py`: local SenseVoiceSmall transcription plus 60-second chunk preservation and FunASR `fa-zh` timestamp-index preparation; no Whisper fallback.
- `process_transcript.py`: transcript cleanup aid.
- `query_symbol_candidates.py`: local symbol candidate lookup.
- `export_to_obsidian.py` / `save_to_my_obsidian.sh`: final Markdown + Word export.
- `validate_utf8_text.py`, `validate_meeting_minutes_contract.py`, `run_meeting_minutes_regression.py`: encoding, Markdown/Word formatting, and sample-regression checks.

## Output Contract

Every final note must follow `references/output_contract.md`, including metadata, speaker-order preservation, heading rules, meeting-type formatting, ambiguity-table shape, and Word style.

If the user asks for optimization later, preserve this simplified structure unless they explicitly request a breaking change.
