# Subagent Guide

默认使用单主流程；只要满足任一高风险条件，就启用对应 subagent。多个条件同时满足时只提高优先级，不改变“任一触发”的原则。最终 Markdown、Word 和归档输出只能由主流程生成。

## 架构

- Main Orchestrator：归档、选择 run profile、调度 subagent、写最终纪要、运行校验和导出。
- Transcript Auditor：只审查转写、时间戳、发言边界和音频/文档冲突。
- Content Integrity Reviewer：只审查内容完整性、标的归因、高风险事实、存疑核验和遗漏。

Subagent 可以输出中间产物，例如：
- 转写质量和时间戳风险。
- 发言边界建议。
- 音频/文档冲突清单。
- 标的和代码候选清单。
- 存疑项核验记录。
- 遗漏检查 findings。

Subagent 不得直接写最终 Markdown、Word 或归档文件。Subagent 的候选正文如果已经压缩、总结、改写人称、改动视角或转成第三人称，只能作为风险提示，不能被主流程复制到终稿。主流程写终稿时只能按原发言顺序整理每个人的发言，并只删除纯口水词、明显 ASR 噪声、无意义重复和重复起手式。

## 调度记录

主流程在成稿前必须保留过程用调度记录，不写入最终纪要正文：

- `transcript_auditor`：`triggered=true/false`、`triggered_by`、`skipped_reason`。
- `content_integrity_reviewer`：`triggered=true/false`、`triggered_by`、`skipped_reason`。
- 若 subagent 不可用，记录失败原因，以及主流程是否完成了等效检查。

## Transcript Auditor

适用：
- 长录音或噪音重。
- 多人边界不清。
- 音频和文稿冲突。
- 时间戳对齐对存疑表很重要。

以上任一条件成立即触发 Transcript Auditor；不要等到所有条件同时满足。

输出重点：
- `transcript_findings`
- `speaker_boundary_findings`
- `timestamp_findings`
- `audio_document_conflicts`
- `requires_main_review`

## Content Integrity Reviewer

适用：
- 多标的混杂。
- 公司名、代码、客户、供应商、数字、日期、术语存疑。
- 推荐对象、比较对象、客户/供应商容易混淆。
- 最终成稿前需要补漏。

以上任一条件成立即触发 Content Integrity Reviewer；不要等到所有条件同时满足。

输出重点：
- `target_attribution_findings`
- `high_risk_claims`
- `doubtful_item_verification`
- `omission_findings`
- `requires_human_review`

核验口径使用 `verification_policy.md`。

## Failure handling

Failure types:
- Subagent unavailable.
- Subagent output missing required fields.
- Subagent contradicts source evidence.
- Subagent adds unsupported content.
- Subagent times out.

Required handling:
- Do not block low-risk document-only work only because subagent is unavailable.
- For high-risk audio jobs, record the failure and continue only if the main workflow can complete equivalent checks.
- If subagent output adds unsupported content, discard that part and rely on source evidence.
- If source conflict remains unresolved, keep source wording, mark doubtful terms, and preserve human confirmation entry.

GO / NO-GO:
- GO: source evidence is sufficient, final writer can preserve order and mark unresolved doubts.
- NO-GO: audio/text is unusable, required current-session materials are missing, or high-risk facts cannot be represented without inventing content.

## Final writer rule

Main Orchestrator writes the final note in one pass using current-session source evidence, applicable subagent findings, `output_contract.md`, and `verification_policy.md`. Findings are inputs, not final prose. The final writer must use source spans over Subagent wording whenever wording fidelity, pronouns, speaker perspective, or speech order differs.
