---
name: investment-meeting-minutes
description: "Use when Codex needs to turn a Chinese investment meeting recording, transcript, or mixed audio+text input into a strict Markdown meeting note with speaker segmentation, company-name correction, stock-symbol validation, source-file archiving, Subagent-assisted intermediate drafts and omission checks, and Markdown/Word export. Triggers include: 整理会议录音, 整理投资会议纪要, 把这段转录整理成纪要, 输出 Obsidian 会议纪要, 校对公司名称和股票代码, 导出 md 和 word, 结合录音与文字整理, 按发言人/版块分段."
---

# Investment Meeting Minutes

## Overview

Produce a strict Chinese investment meeting note from the current meeting's audio, transcript, document, or mixed materials. Preserve the speaker's meaning, validate names and stock codes before writing confirmed entities, and export the human-confirmed Markdown + Word note.

The operating model is Subagent-priority with a single final writer. Use Subagents to improve coverage, factual checking, and text quality, but write final Markdown, Word, archive outputs, and sync payloads only through the main workflow.

For Dify workflow integration, read `references/dify_adapter_guide.md`.

## Stable Contract

- Workflow after input archive: 转录 -> 校对 -> 识别 -> 编辑 -> 排版.
- Source boundary: use only current-session materials as meeting-content sources. External sources may verify names, codes, terms, or public facts, but must not add meeting content.
- ASR: use local SenseVoice only. Do not switch to Whisper or another ASR. If SenseVoice cannot run, continue only with provided text or an existing transcript.
- Final writer: Subagents may produce intermediate notes, candidate blocks, verification notes, and omission findings; they must not directly write final deliverables.
- Meeting type: default to `多人复盘会`. Use `上市公司交流` only for a single-company special meeting. Use `专家交流` only for expert Q&A. Do not create `其他`.
- Segmentation: organize `## 一、发言整理` by `发言人/版块`, not by one-target-per-section. Each paragraph or subsection heading must include all targets mentioned in that paragraph or subsection.
- Doubtful items: non-person doubtful content must run the stable verification prompt in `references/evidence_policy.md`.
- Validators: keep validation to encoding, Markdown/Word structure, and regression samples. Do not add content-direction validators or Subagent-output validators.

## Workflow

### 0. Prepare Inputs

Archive raw files before transcription or writing. Use `scripts/archive_raw_inputs.py`; read `references/archive_naming_contract.md` before changing archive/export naming or archive bridges.

Handle source modes:
- `audio_only`: archive, then transcribe with SenseVoice.
- `document_only`: archive, then organize from the provided text/document.
- `audio_plus_document`: archive both; use both as evidence and keep conflicts visible.

Keep Chinese text files and generated Markdown/TXT/JSON/YAML as UTF-8 without BOM. In Python text I/O, pass `encoding="utf-8"`. If UTF-8 decoding fails or replacement characters appear, stop and report the affected file.

### 1. 转录

When audio is provided, use `scripts/transcribe_audio.py` for local SenseVoice transcription. For production-like audio, read `references/runtime_readiness_guide.md` and run `scripts/check_investment_workflow_health.py --strict`.

### 2. 校对

Use `scripts/process_transcript.py` when text is long, noisy, or missing clear speaker boundaries. Correct obvious ASR noise while preserving the speaker's viewpoint, order, uncertainty, and meaningful wording.

Use the Transcript Auditor Subagent when audio is long, noisy, multi-speaker, has unclear speaker boundaries, or has audio/document conflicts.

### 3. Correct names and symbols

Use references only when they match the uncertainty:
- `references/proofreading_guide.md`: ASR cleanup, speaker naming, company names, abbreviations, and industry terms.
- `references/symbol_sources.md`: stock-code lookup order and local candidate sources.
- `references/evidence_policy.md`: stable verification prompt for non-person doubtful items.
- `references/target_attribution_policy.md`: target roles, investment actions, and heading coverage.

Rules:
- Start from meeting context before choosing a company, ticker, term, customer, supplier, number, date, or event.
- Confirm company names and stock codes before writing them as facts. Local candidates and ASR output are clues, not proof.
- Use `a-stock-data` live sources when available; use `scripts/query_symbol_candidates.py` only as a candidate generator.
- If a non-person item cannot be confirmed, keep the source wording, mark the doubtful fragment, and put it in `## 二、存疑与待确认`.
- Ignore pure person-name uncertainty unless it changes an investment fact or attribution.

Use the Content Integrity Reviewer Subagent when target attribution, multi-target headings, high-risk facts, doubtful-item verification, or omission checks would materially reduce errors.

### 4. 编辑

Write one unified draft. Use `references/default_output_template.md` and `references/output_format_guide.md`. The final note must contain reader-facing metadata, then `## 一、发言整理`, then `## 二、存疑与待确认` only when real uncertainty exists.

Preserve actual speech order and speaker perspective. If a speaker appears multiple times, keep later turns in their real position. Segment by `发言人/版块`; each paragraph or subsection heading must include all targets mentioned in that paragraph or subsection. Do not include workflow debugging fields such as `输入来源`, `整理说明`, tool names, logs, paths, review URLs, draft IDs, or draft-stage explanations.

### 5. 排版

After final Markdown confirmation, validate and export:

```bash
python3 scripts/validate_utf8_text.py NOTE.md --require-cjk
python3 scripts/validate_meeting_minutes_contract.py NOTE.md --json
python3 scripts/export_to_obsidian.py NOTE.md
```

The exporter writes one Markdown file and one Word file. Do not generate PDF. If Word export, knowledge-base sync, or Google Drive sync fails, keep local outputs and report the failure without deleting files.

## Reference Routing

- Dify integration: `references/dify_adapter_guide.md`.
- Output structure and meeting-type formatting: `references/output_format_guide.md`.
- Word style: `references/word_export_style_reference.md`.
- Archive/export naming: `references/archive_naming_contract.md`.
- Runtime readiness: `references/runtime_readiness_guide.md`.
- Name/code/entity proofreading: `references/proofreading_guide.md`, `references/symbol_sources.md`.
- Target attribution and heading coverage: `references/target_attribution_policy.md`.
- Doubtful-item verification prompt: `references/evidence_policy.md`.
- Subagent workflow and failure handling: `references/subagent_workflow.md`, `references/subagent_failure_policy.md`.

## Resources

Core scripts:
- `archive_raw_inputs.py`: copy current raw files into the workflow archive.
- `transcribe_audio.py`: local SenseVoice transcription; no Whisper fallback.
- `process_transcript.py`: transcript cleanup aid.
- `query_symbol_candidates.py`: local symbol candidate lookup.
- `export_to_obsidian.py` / `save_to_my_obsidian.sh`: final Markdown + Word export.
- `validate_utf8_text.py`, `validate_meeting_minutes_contract.py`, `run_meeting_minutes_regression.py`: encoding, Markdown/Word formatting, and sample-regression checks.

## Output Contract

Every final note must include:
- Meeting metadata.
- Meeting series metadata (`会议系列`) for grouping and downstream processing.
- `## 一、发言整理` in actual speech order, segmented by `发言人/版块`, with headings covering all targets mentioned in each paragraph or subsection.
- `## 二、存疑与待确认` only when real doubtful content exists.

If the user asks for optimization later, preserve this simplified structure unless they explicitly request a breaking change.
