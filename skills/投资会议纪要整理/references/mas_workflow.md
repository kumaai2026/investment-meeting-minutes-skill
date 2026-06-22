# Skill-first MAS 工作流

本文件定义会议纪要 skill 的 Skill-first、Contract-first、MAS-ready 工作方式。它不是重型多 Agent 框架，不要求 LangGraph、CrewAI、AutoGen，也不改变最终 Markdown/Word 输出 contract。

## 原则

- 最终正文仍由基础 skill 和已选会议类型 skill 控制。
- Dify 仍是上传、转写/抽取、人工初审、二审、归档确认和同步的 adapter。
- MAS sidecar 是内部交接物，不进入终稿正文。
- 信息准确性优先于可读性美化；不得为了标题简洁遗漏真实主标的或推荐标的。
- Intake、Structure、Drafting、Export QA 优先是 contract/script role，不默认作为 LLM agent。
- Codex subagents 只在复杂、多标的、高风险校对场景显式启用。

## 输入形态

### audio_only

只有音频、无人工文稿。

要求：
- 先运行 SenseVoice/FunASR 转写或使用已存在的同会话转写稿。
- 生成 `source_profile` 和 `transcript_audit`。
- 将低置信词、发言人边界、时间戳、疑似公司名/代码写入 sidecar。
- 存疑正文标注必须使用可靠时间戳；不得从清洗后正文比例估算。

### document_only

只有文档、文字稿、人工转写稿或 Dify 文本抽取结果。

要求：
- 跳过音频转写。
- 生成 `source_profile`、`segmentation_plan`、`target_attribution_ledger`、`evidence_ledger`。
- 重点处理结构分段、标的归因、证据核验和近原文整理。
- 正文存疑词只加粗，不写时间戳占位；存疑表时间戳写 `未提供`。

### audio_plus_document

同时有音频和文档。

要求：
- 音频和文档互为校对证据，不能无条件互相覆盖。
- 冲突内容进入 `transcript_audit` 或 `suspect_confirmation`。
- 如果音频、文档和外部证据不能统一，保留原始表述并写入存疑表。

## 交接链路

标准链路：

```text
source_profile
-> transcript_audit
-> segmentation_plan
-> target_attribution_ledger
-> evidence_ledger
-> suspect_confirmation
-> draft
-> red_team_review
-> export_qa
```

### source_profile

记录输入形态和边界。它回答“本次会议允许使用哪些材料”。

必须覆盖：
- `input_mode`: `audio_only` / `document_only` / `audio_plus_document`
- `files`
- `meeting_type_candidate`
- `has_audio`
- `has_document`
- `has_timestamp`
- `known_speakers`
- `known_targets`
- `sensitive_terms`
- `processing_notes`

### transcript_audit

仅在有音频或带时间戳转写时必需。它回答“转写是否可靠，哪里需要人工确认”。

必须覆盖：
- speaker boundary issues
- timestamp anchors
- low-confidence words
- ASR conflicts
- audio/document conflicts
- suspected company names, codes, terms, customers, numbers

### segmentation_plan

回答“正文应按什么真实顺序和主题拆分”。

要求：
- 真实发言顺序优先。
- 不合并同一发言人的非连续发言。
- 一段话涉及多个标的时，按主标的、推荐标的、比较对象和背景对象拆分或在标题中覆盖。
- 不改变既有会议类型体系。

### target_attribution_ledger

回答“每段话的主标的和推荐标的是什么”。

必须遵守 `target_attribution_policy.md`。

### evidence_ledger

回答“公司名、代码、术语、客户名、数字、订单、产能、价格是否有证据支持”。

必须遵守 `evidence_policy.md`。

### suspect_confirmation

回答“哪些内容不能确认，人工应怎么确认”。

每条必须有：
- source span or source reference
- context judgment
- uncertainty reason
- candidate values
- suggested confirmation path
- final handling in draft

### draft

正式草稿仍使用当前类型 skill 生成。不得把 sidecar 原样写进终稿。

### red_team_review

检查：
- 标题是否遗漏主标的或推荐标的。
- 背景/比较标的是否误判为推荐标的。
- 第一人称、条件表达、否定表达、数字单位是否被改写。
- 存疑是否正文标注并进入表格。
- 是否出现旧版四段式或过程字段。

### export_qa

优先由脚本执行：
- `validate_meeting_minutes_contract.py`
- `validate_word_export.py`
- `validate_utf8_text.py`
- `validate_mas_artifacts.py`

LLM 只解释失败原因和建议修复，不代替脚本判定。

## MAS 触发条件

启用 MAS sidecar：
- `audio_only`
- `audio_plus_document`
- 多人复盘会
- 一段话涉及多个公司、股票或标的
- 涉及推荐、看多、看空、建议关注、重点跟踪、买入、卖出、加仓、减仓
- 涉及公司名、股票代码、客户名、订单、数字、产能、价格、收入、利润
- 上一轮出现标题标的不全、推荐标的识别错误、术语错漏、第一人称改写错误

可以保持单流程：
- 文本很短
- 只做格式转换
- 不涉及标的、公司名、代码、订单、数字
- 用户明确要求快速草稿

## 终稿污染禁止

最终 Markdown/Word 不得出现：
- `source_profile`
- `transcript_audit`
- `segmentation_plan`
- `target_attribution_ledger`
- `evidence_ledger`
- `suspect_confirmation`
- `draft_review_report`
- `qa_report`
- review URL / draft ID / history URL
- 工具日志、路径、Traceback
- `AI结构化总结`、`标的汇总表`
