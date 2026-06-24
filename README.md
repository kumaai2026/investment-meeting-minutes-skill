# 投资会议纪要整理 Skill

这个仓库保存 Codex 使用的中文投资会议纪要整理 skill 包，用于把投资研究场景中的会议录音、转写稿、纪要草稿或音频+文字混合材料，整理成可人工复核、可归档、可同步知识库的 Markdown 和 Word 会议纪要。

当前定位是 **Skill-first + conditional Subagents**。它不是完整 MAS，也不引入 LangGraph、CrewAI、AutoGen 等重型 Agent 框架。

## 核心原则

- Main Orchestrator 是最终 Markdown、Word、归档和同步产物的唯一写作者。
- Subagents 只读审查并返回结构化 findings，不直接修改终稿。
- 会议类型 skill 仍是最终输出格式权威。
- Deterministic validators 决定硬性 GO/NO-GO。
- Dify 仍是上传、抽取/转写、人工关口、归档确认和同步 adapter。
- Dify subagent execution is unverified; existing single-agent fallback remains authoritative.

## Skill 包内容

- `skills/投资会议纪要整理`：基础 skill，定义归档、转录、预处理、Subagent 触发、校对、格式、复核、导出、同步和验证规则。
- `skills/投资会议纪要-多人复盘会`：用于多名发言人轮流复盘市场、板块、标的和仓位动作。
- `skills/投资会议纪要-上市公司交流`：用于上市公司管理层交流、业绩会和调研纪要。
- `skills/投资会议纪要-专家交流`：用于专家电话会、产业链访谈、渠道调研和主题深访。
- `skills/投资会议纪要-其他`：用于不属于以上三类的自定义中文投研会议。
- `skills/meeting-minutes-sanitizer`：用于中文投研会议纪要脱敏。
- `.codex/agents/transcript-auditor.toml`：只读 Transcript Auditor。
- `.codex/agents/content-integrity-reviewer.toml`：只读 Content Integrity Reviewer，支持 `pre_draft` 和 `post_draft`。
- `.codex/config.toml`：限制 custom agent 并发和派生深度。

## Conditional Subagents

### Transcript Auditor

用于 `audio_only`、存在音频/文稿冲突的 `audio_plus_document`、发言人边界不清、关键实体/代码/数字/术语低置信、或需要可靠时间锚点的场景。

输出只进入内部 `analysis_ledger.json`，不得写终稿。

### Content Integrity Reviewer

`pre_draft` 负责主标的、推荐标的、客户/供应商/竞争对手/比较对象、高风险事实、拆段和标题建议。

`post_draft` 负责对照原材料、analysis ledger 和草稿，检查标题覆盖、推荐标的误判、动作/立场漂移、第一人称/否定/条件表达、数字单位、存疑标注、会议类型 contract 和过程字段污染。

正式会议纪要默认运行 post-draft review；纯格式转换或明确要求快速非正式草稿时可跳过。

## 输入模式

- `audio_only`：原始材料 -> ASR -> 条件式 Transcript Auditor -> 人工初审 -> pre_draft Reviewer -> Main Orchestrator 写草稿 -> post_draft Reviewer -> 脚本校验 -> 人工二审 -> 导出。
- `audio_plus_document`：同上，但音频和文稿互为证据；未经确认的 ASR 不得在人工初审前作为高置信标的归因输入。
- `document_only`：文稿 -> 输入确认/人工初审 -> pre_draft Reviewer -> Main Orchestrator 写草稿 -> post_draft Reviewer -> 脚本校验 -> 人工二审 -> 导出。

## Internal Artifacts

旧的多 sidecar 链路已收敛为两个内部产物：

- `analysis_ledger.json`
- `qa_report.json`

默认隔离目录：

```text
.meeting-minutes-internal/
```

这些产物不得进入最终 Markdown/Word、Dify 知识库、Google Drive 同步输出或 sanitizer RAG 输出。

## Validators

常用检查：

```bash
python3 skills/投资会议纪要整理/scripts/validate_utf8_text.py README.md skills/*/SKILL.md --require-cjk --portable-skill
python3 skills/投资会议纪要整理/scripts/run_meeting_minutes_regression.py --json
python3 skills/投资会议纪要整理/scripts/validate_meeting_minutes_contract.py NOTE.md --json
python3 skills/投资会议纪要整理/scripts/validate_word_export.py NOTE.docx --markdown NOTE.md --json
python3 skills/投资会议纪要整理/scripts/validate_analysis_ledger.py .meeting-minutes-internal/analysis_ledger.json --qa-report .meeting-minutes-internal/qa_report.json --json
python3 skills/投资会议纪要整理/scripts/validate_title_target_consistency.py NOTE.md .meeting-minutes-internal/analysis_ledger.json --json
python3 skills/投资会议纪要整理/scripts/score_target_attribution.py --actual ACTUAL.json --gold GOLD.json --json
python3 skills/投资会议纪要整理/scripts/validate_custom_agents.py --json
```

`validate_meeting_minutes_contract.py` 的实际规则是：必须有会议元信息和 `## 一、逐发言人原文整理`；只有存在真实存疑时才输出 `## 二、存疑与待确认`。

## Live Smoke Test

修改 custom agents 后，当前 Codex 会话可能不会重新加载新 agent。若 live spawn 不可用，应记录：

```text
PROJECT CUSTOM AGENT LIVE SPAWN = RESTART REQUIRED
```

静态 schema 仍必须通过。Dify subagent 状态只能写 `PASS`、`FAIL` 或 `UNVERIFIED`。

## 隐私边界

不要提交：

- 真实会议材料、原始录音、正式纪要或私有转写。
- 私有绝对路径、review URL、draft URL、token、cookie、API key、Authorization/Bearer header。
- ASR 模型权重、下载缓存、虚拟环境或本机私有配置。

公共 fixtures 必须是合成或充分脱敏内容。

## 已知限制

- Dify 派生 Codex Subagent 尚未验证，Dify 仍以单 Agent fallback 为权威。
- Custom agent live spawn 可能需要重启 Codex 才能加载新 `.codex/agents` 文件。
- 真实生产启用前仍需要脱敏 blind-run 数据验证。
- Word 导出依赖 `python-docx`。
