# 投资会议纪要整理 Skill

这个仓库保存 Codex 使用的中文投资会议纪要整理 skill 包，用于把投资研究场景中的会议录音、转写稿、纪要草稿或音频+文字混合材料，整理成可人工复核、可归档、可同步知识库的 Markdown 和 Word 会议纪要。

当前定位是 **Subagent-priority + single final writer**：优先使用 subagent 提高信息完整性、事实准确度和文本质量，但最终 Markdown、Word、归档和同步产物只由主流程统一生成。

## 核心原则

- Subagent 可以输出结构化中间产物，例如发言整理候选、标的/代码清单、存疑核验清单、音频/文档冲突摘要和遗漏检查。
- 主流程是最终会议纪要的唯一写作者，避免多 agent 直接拼接造成格式、口径和风格割裂。
- 基础 skill 是唯一会议纪要 skill；会议类型只影响最终格式细节。
- 主 workflow 固定为：转录 -> 校对 -> 识别 -> 编辑 -> 排版。
- `发言整理` 按 `发言人/版块` 分段；每段标题覆盖该段提到的全部标的，不强制一个标的一段。
- 非人名存疑项统一调用 `references/evidence_policy.md` 中的稳定核验 prompt。
- Validator 只检查格式、章节、表头、Word 样式、编码和样例回归，不伪验证联网核验是否真实发生。
- Dify 只是上传、抽取/转写、人工关口、归档确认和同步 adapter；具体规则见 `skills/投资会议纪要整理/references/dify_adapter_guide.md`。

## Skill 包内容

- `skills/投资会议纪要整理`：基础 skill，定义输入归档、转录、校对、识别、编辑、排版、导出和同步规则。
- 会议类型规则内置在基础 skill 中：默认 `多人复盘会`；明确单家公司专场时用 `上市公司交流`；明确专家问答时用 `专家交流`。
- `skills/meeting-minutes-sanitizer`：用于中文投研会议纪要脱敏。
- `.codex/agents/transcript-auditor.toml`：转写、时间戳、发言边界和音频/文档冲突 subagent。
- `.codex/agents/content-integrity-reviewer.toml`：内容完整性、标的归因、存疑核验和最终补漏 subagent。

## Subagent 使用场景

- `audio_only`：原始材料 -> SenseVoice -> Transcript Auditor -> 人工初审 -> Content Integrity Reviewer -> 主流程写草稿 -> 最终补漏检查 -> 脚本格式校验 -> 人工二审 -> 导出。
- `audio_plus_document`：同上，但音频和文稿互为证据；冲突内容必须进入候选或存疑核验，不得自动覆盖。
- `document_only`：文稿 -> 输入确认/人工初审 -> Content Integrity Reviewer -> 主流程写草稿 -> 最终补漏检查 -> 脚本格式校验 -> 人工二审 -> 导出。

优先触发 subagent 的情况：长录音、噪音重、多人边界不清、音频与文档冲突、多标的混杂、名称/代码/数字/客户/供应商/术语存疑、最终成稿前需要补漏。

## Validators

常用检查：

```bash
python3 skills/投资会议纪要整理/scripts/validate_utf8_text.py README.md skills/*/SKILL.md --require-cjk --portable-skill
python3 skills/投资会议纪要整理/scripts/run_meeting_minutes_regression.py --json
python3 skills/投资会议纪要整理/scripts/validate_meeting_minutes_contract.py NOTE.md --json
python3 skills/投资会议纪要整理/scripts/validate_meeting_minutes_contract.py NOTE.md --word NOTE.docx --json
```

`validate_meeting_minutes_contract.py` 的规则是：必须有会议元信息和 `## 一、发言整理`；只有存在真实存疑时才输出 `## 二、存疑与待确认`；存疑表必须使用固定表头并保留空白 `人工确认` 列；传入 `--word` 时同时检查 Word 导出结构和存疑词样式。

## 隐私边界

不要提交：

- 真实会议材料、原始录音、正式纪要或私有转写。
- 私有绝对路径、review URL、draft URL、token、cookie、API key、Authorization/Bearer header。
- ASR 模型权重、下载缓存、虚拟环境或本机私有配置。

公共 fixtures 必须是合成或充分脱敏内容。

## 已知限制

- Custom agent live spawn 可能需要重启 Codex 才能加载新 `.codex/agents` 文件。
- 真实生产启用前仍需要脱敏 blind-run 数据验证。
- Word 导出依赖 `python-docx`。
