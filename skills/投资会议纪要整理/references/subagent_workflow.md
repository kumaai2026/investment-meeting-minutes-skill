# Subagent-Priority Workflow

Use this file when a meeting is long, noisy, multi-speaker, multi-target, or fact-sensitive enough that a single-pass writer is likely to miss information or distort meaning. Subagents are risk-triggered reviewers, not the default path for every meeting.

The workflow is Subagent-priority with a single final writer. Subagents may produce structured intermediate material, but the main workflow is the only writer of final Markdown, Word, archive, and sync artifacts.

For short, clean `document_only` sources with clear speakers and low entity uncertainty, skip Subagents and run the single-writer path plus formatting validators. Use Subagents only for the risk triggers below or when human review asks for an omission/distortion check.

## Architecture

```text
Source material
-> SenseVoice or provided text
-> Subagent intermediate work when risk triggers apply
-> Main workflow writes one unified draft
-> Subagent omission/distortion check when needed
-> Formatting validators and human review
-> Export, archive, and sync
```

## Subagent Roles

### Transcript Auditor

Use for:

- `audio_only`
- `audio_plus_document` with audio/document conflict
- unclear speaker boundaries
- low-confidence company names, stock codes, numbers, units, or technical terms
- need for reliable time anchors

Allowed output:

- speaker-boundary findings
- reliable or missing time anchors
- low-confidence spans
- audio/document conflict notes
- possible entities requiring review

### Content Integrity Reviewer

Use before or after drafting when:

- one semantic segment contains multiple targets
- a source contains recommendation, buy, sell, add, reduce, avoid, or another investment action
- main discussion object and action object may differ
- customers, suppliers, competitors, comparable companies, upstream/downstream entities, or background entities appear
- orders, capacity, price, profit, revenue, gross margin, valuation, market cap, or other high-risk facts appear
- the draft may have omitted, compressed, or changed source meaning

Allowed output:

- candidate `发言整理` blocks
- target/company/code candidate lists
- suggested splits and headings
- doubtful-item verification notes using the stable prompt in `evidence_policy.md`
- high-risk fact findings
- omission and distortion findings

## Final Writer Rule

The main workflow must consolidate all useful intermediate material into one final note. Do not directly paste subagent logs, JSON, status fields, file paths, review URLs, or debug explanations into the final Markdown.

Subagent output should improve coverage and accuracy, not create a second final-note format.

## Failure And Fallback

If a subagent is unavailable, times out, or returns unusable output:

- Do not claim the review passed.
- Continue with single-writer processing only when the source risk is acceptable.
- Keep existing human confirmation gates.
- Preserve unresolved high-risk issues in `## 二、存疑与待确认` or report that human review is required.
- Do not write failure details into the final note body.

See `subagent_failure_policy.md`.
