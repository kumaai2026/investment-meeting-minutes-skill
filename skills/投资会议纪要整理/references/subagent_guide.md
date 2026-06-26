# Subagent Guide

默认使用单主流程；只有当来源长、噪音重、冲突多、多标的混杂或事实风险高时才启用 subagent。最终 Markdown、Word、归档输出和同步 payload 只能由主流程生成。

## 架构

- Main Orchestrator：归档、选择 run profile、调度 subagent、写最终纪要、运行校验和导出。
- Transcript Auditor：只审查转写、时间戳、发言边界和音频/文档冲突。
- Content Integrity Reviewer：只审查内容完整性、标的归因、高风险事实、存疑核验和遗漏。

Subagent 可以输出中间产物，例如：
- 转写质量和时间戳风险。
- 发言边界建议。
- 音频/文档冲突摘要。
- 标的和代码候选清单。
- 存疑项核验记录。
- 遗漏检查 findings。

Subagent 不得直接写最终 Markdown、Word、归档文件或知识库同步内容。

## Transcript Auditor

适用：
- 长录音或噪音重。
- 多人边界不清。
- 音频和文稿冲突。
- 时间戳对齐对存疑表很重要。

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
- For high-risk audio/Dify jobs, record the failure and continue only if the main workflow can complete equivalent checks.
- If subagent output adds unsupported content, discard that part and rely on source evidence.
- If source conflict remains unresolved, keep source wording, mark doubtful terms, and preserve human confirmation entry.

GO / NO-GO:
- GO: source evidence is sufficient, final writer can preserve order and mark unresolved doubts.
- NO-GO: audio/text is unusable, required current-session materials are missing, or high-risk facts cannot be represented without inventing content.

## Final writer rule

Main Orchestrator writes the final note in one pass using current-session source evidence, applicable subagent findings, `output_contract.md`, and `verification_policy.md`. Findings are inputs, not final prose.
