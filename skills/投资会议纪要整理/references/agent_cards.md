# MAS 角色卡

本文件定义角色分工。角色不等于必须启动独立 subagent；只有复杂场景才显式使用 Codex subagents。

## Intake Role

默认执行方式：contract/script role。

职责：
- 建立 `source_profile`。
- 判断输入形态：`audio_only`、`document_only`、`audio_plus_document`。
- 确认会议日期、标题、类型、系列、已知发言人、已知标的、敏感词。
- 明确本次会议可使用的 source materials。

禁止：
- 跨会话取历史材料补内容。
- 把历史纪要作为本次会议内容来源。
- 将原始路径或工具日志写入终稿。

## Transcript Agent

默认执行方式：有音频时可启用 agent；无音频时跳过。

职责：
- 审计 SenseVoice/FunASR 转写。
- 输出 `transcript_audit`。
- 标出发言人边界不稳、低置信词、时间戳锚点、疑似代码、数字和术语。
- 对 `audio_plus_document` 标出音频和文档冲突。

禁止：
- 写终稿。
- 用 Whisper 或其他 ASR 替代 SenseVoice/FunASR。
- 自动用文稿覆盖音频，或用音频覆盖文稿。

## Structure Role

默认执行方式：contract role。

职责：
- 选择既有会议类型 skill：多人复盘会、上市公司交流、专家交流、其他。
- 生成 `segmentation_plan`。
- 保留真实发言顺序。
- 标出需要拆段或多标的标题覆盖的段落。

禁止：
- 新增、合并、重命名会议类型。
- 为了归并同一发言人而打乱真实顺序。

## Target Attribution Agent

默认执行方式：复杂多标的场景显式启用。

职责：
- 输出 `target_attribution_ledger`。
- 检查每个段落的 `primary_target`、`mentioned_targets`、`recommendation_target`、`target_roles`。
- 检查标题是否遗漏标的。
- 检查真实推荐标的是否被背景标的、比较标的、上下游标的覆盖。
- 给出需要修复的段落和修复建议。

禁止：
- 因出现次数多就默认某公司是推荐标的。
- 把客户、供应商、竞争对手、指数、行业背景标的当作推荐对象。
- 抢最终写作权。

## Evidence & Suspect Confirmation Agent

默认执行方式：复杂或高风险校对场景显式启用。

职责：
- 输出 `evidence_ledger` 和 `suspect_confirmation`。
- 核验公司名、股票代码、术语、客户名、数字、订单、产能、价格、收入、利润。
- 区分 source evidence、local reference evidence、external verification path。
- 对无法确认的信息提出人工确认路径。

禁止：
- 用外部证据编造会议没有说过的结论。
- 把本地候选查询当作最终确认。
- 在存疑表只写“待确认”。

## Drafting Role

默认执行方式：主流程和类型 skill 执行。

职责：
- 根据已确认 source、`segmentation_plan`、`target_attribution_ledger`、`evidence_ledger`、`suspect_confirmation` 输出近原文草稿。
- 遵守当前 Markdown 输出 contract。
- 保留第一人称、条件表达、否定表达、数字单位和发言边界。

禁止：
- 自行扩写投资结论。
- 输出 MAS sidecar 字段。
- 将近原文改写成研报摘要。

## Red-team Agent

默认执行方式：复杂或高风险草稿显式启用。

职责：
- 输出 `draft_review_report`。
- 查找遗漏、幻觉、第一人称改写、标题覆盖不全、真实推荐标的识别错误、存疑未入表。
- 检查旧版四段式和过程字段污染。

禁止：
- 重写整篇终稿。
- 改变会议类型或最终 contract。

## Export QA

默认执行方式：script role。

职责：
- 输出 `qa_report`。
- 运行 contract、UTF-8、Word export 和 MAS sidecar 校验。
- 将失败项映射到具体文件、段落或 artifact。

禁止：
- 用 LLM 判断代替脚本结果。
- 在校验失败时继续宣称 GO。
