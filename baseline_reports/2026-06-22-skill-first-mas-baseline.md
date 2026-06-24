# Skill-first MAS Baseline

Baseline date: 2026-06-22
Repository: `<repo-root>`
Branch at capture: `main`
HEAD at capture: `0682da2f44be2aa2a96ff52e25d03cb3525d8657`
Git status at capture: `main...origin/main`, no local changes

## Repository Shape

- Base skill: `skills/投资会议纪要整理`
- Type skills:
  - `skills/投资会议纪要-多人复盘会`
  - `skills/投资会议纪要-上市公司交流`
  - `skills/投资会议纪要-专家交流`
  - `skills/投资会议纪要-其他`
- Sanitizer skill: `skills/meeting-minutes-sanitizer`
- Baseline references: 8 Markdown files under `skills/投资会议纪要整理/references`
- Baseline regression samples: 6 Markdown samples plus `cases.json`
- Meeting-minutes scripts: 28 Python/shell entrypoints under `skills/投资会议纪要整理/scripts`

## Baseline Commands And Results

```bash
python3 <skill-creator>/scripts/quick_validate.py skills/投资会议纪要整理
python3 <skill-creator>/scripts/quick_validate.py skills/投资会议纪要-多人复盘会
python3 <skill-creator>/scripts/quick_validate.py skills/投资会议纪要-上市公司交流
python3 <skill-creator>/scripts/quick_validate.py skills/投资会议纪要-专家交流
python3 <skill-creator>/scripts/quick_validate.py skills/投资会议纪要-其他
python3 <skill-creator>/scripts/quick_validate.py skills/meeting-minutes-sanitizer
```

Result: all six skill folders returned `Skill is valid!`.

```bash
python3 skills/投资会议纪要整理/scripts/run_meeting_minutes_regression.py --json
```

Result: `ok=true`, `case_count=6`, all baseline cases passed:

- `文本-only 样例`
- `音频转写-only 样例`
- `音频+文稿 样例`
- `多人复盘会类型样例`
- `上市公司交流类型样例`
- `专家交流类型样例`

```bash
python3 skills/投资会议纪要整理/scripts/validate_utf8_text.py README.md skills/投资会议纪要整理/SKILL.md skills/投资会议纪要-多人复盘会/SKILL.md skills/投资会议纪要-上市公司交流/SKILL.md skills/投资会议纪要-专家交流/SKILL.md skills/投资会议纪要-其他/SKILL.md skills/meeting-minutes-sanitizer/SKILL.md --require-cjk --portable-skill
```

Result: README and all six `SKILL.md` files returned `ok`.

```bash
python3 skills/投资会议纪要整理/scripts/validate_meeting_minutes_contract.py skills/投资会议纪要整理/references/regression_samples/text_only.md --source-mode document --json
python3 skills/投资会议纪要整理/scripts/validate_meeting_minutes_contract.py skills/投资会议纪要整理/references/regression_samples/audio_only.md --source-mode audio --require-audio-timestamps --json
```

Result: both returned `ok=true`, with no errors or warnings.

```bash
python3 skills/投资会议纪要整理/scripts/validate_word_export.py "<workflow-root>/01 Projects/会议纪要/YYYY-MM-DD/<redacted-note.docx>" --markdown "<workflow-root>/01 Projects/会议纪要/YYYY-MM-DD/<redacted-note.md>" --json
```

Result: `ok=true`, `paragraph_count=317`, `run_count=249`.

```bash
python3 skills/投资会议纪要整理/scripts/validate_utf8_text.py "<workflow-root>/01 Projects/会议纪要/YYYY-MM-DD/<redacted-note.md>" "<workflow-root>/01 Projects/会议纪要/YYYY-MM-DD/<redacted-note.docx>" --require-cjk
```

Result: both files returned `ok`.

## GO / NO-GO Comparison Rules

GO after the Skill-first MAS upgrade requires:

- All six baseline regression cases still pass.
- At least one `document_only` MAS sample passes.
- At least one `audio_only` or `audio_plus_document` MAS sample passes.
- Word export validation passes on the same sampled Markdown/Word pair.
- Final Markdown does not contain MAS sidecar fields, review URLs, tool logs, or old four-section output.
- Segment titles cover the true primary target and recommendation target when those differ.
- Background, comparison, customer, supplier, competitor, and incidental mentions are not treated as recommendation targets.

NO-GO if any of these occur:

- Any old regression contract fails.
- Word export validation regresses.
- Final notes contain process-only fields such as `source_profile`, `evidence_ledger`, review URLs, tool logs, `AI结构化总结`, or `标的汇总表`.
- Meeting types are renamed, merged, or deleted.
- A title omits the core recommendation target.
- A background or comparison target is misclassified as the recommendation target.
- First-person statements, conditional language, negative statements, or numeric units are systematically rewritten.
