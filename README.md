# 投资会议纪要整理 Skill

这个仓库保存 Codex 使用的中文投资会议纪要整理 skill 包，用于把投资研究场景中的会议录音、转写稿、纪要草稿或音频+文字混合材料，整理成可人工复核、可归档、可同步知识库的 Markdown 和 Word 会议纪要。

它的核心目标不是生成压缩摘要，而是保留接近原始发言的信息密度：按真实发言顺序整理，去除无意义口水词和明显 ASR 噪声，校正公司名、股票代码、行业术语、数字和专有名词，并把不能确认的内容放入带时间戳的存疑表。

## Skill 包内容

- `skills/投资会议纪要整理`：基础 skill，定义归档、转录、预处理、校对、格式、复核、导出、同步和验证规则。
- `skills/投资会议纪要-多人复盘会`：用于多名发言人轮流复盘市场、板块、标的和仓位动作。
- `skills/投资会议纪要-上市公司交流`：用于上市公司管理层交流、业绩会和调研纪要。
- `skills/投资会议纪要-专家交流`：用于专家电话会、产业链访谈、渠道调研和主题深访。
- `skills/投资会议纪要-其他`：用于不属于以上三类的自定义中文投研会议。
- `skills/meeting-minutes-sanitizer`：用于中文投研会议纪要脱敏，删除发言人身份和发言风格，输出 `<原文件名>_sanitized.docx` 与 `<原文件名>_rag.jsonl`。

## 适用输入

支持以下输入形态：

- 音频：如 `mp3`、`m4a`、`wav` 等会议录音。
- 文稿：如 `txt`、`md`、`docx`、Dify 文本抽取结果或人工转写稿。
- 音频+文稿：以音频转写为主，文稿作为校正参考。
- Dify 工作流字段：`combined_text`、`text_reference`、`sensevoice_transcript`、`meeting_title`、`meeting_type`、`meeting_series`、`input_reviewed` 等。
- 用户补充信息：会议日期、会议标题、会议类型、会议系列、发言人名单、标的提示、需要重点校对的术语或代码。

## 预期输出

最终纪要默认输出为 Markdown + Word，不生成 PDF。

终稿必须包含：

- 读者可见的元信息：`会议日期`、`整理时间`、`会议标题`、`会议类型`、`会议系列`，上市公司交流还应包含 `会议标的`。
- `## 一、逐发言人原文整理`：按真实发言顺序整理后的近原文内容。
- `## 二、存疑与待确认`：固定表头为 `时间戳 | 原始表述 | 当前判断 | 存疑原因 | 候选项 | 人工确认`。
- 正文中的存疑词：必须加粗，并紧跟 `（存疑时间戳：HH:MM:SS）`；无法定位时使用 `未提供`。
- Word 导出中的存疑词：应显示为加粗 + 下划线，方便人工校对。

不会在终稿中输出：

- 工具日志、运行路径、输入来源、整理说明等流程字段。
- 未经人工确认的初始转写稿或模型草稿。
- 旧版四段式内容，如 `AI结构化总结`、`标的汇总表` 等。

## 处理流程

| 步骤 | 做什么 | 使用的大模型/服务 | MCP/本地工具 | 外部数据和证据 |
| --- | --- | --- | --- | --- |
| 1. 原始材料归档 | 先复制所有原始音频、文稿、附件，不移动用户原文件 | 无 | `archive_raw_inputs.py`、Dify `/archive-inputs` 桥接服务 | 本地 Obsidian 工作流目录、Google Drive 同步目标 |
| 2. 音频转写 | 将录音转成可复核文本，优先带说话人和句级时间戳 | SenseVoice `iic/SenseVoiceSmall`，FunASR VAD，cam++ 说话人分离 | `transcribe_audio.py`、`sensevoice_transcription_server.py` | 本地 FunASR/ModelScope 模型缓存 |
| 3. 辅助转写比对 | 交叉检查公司名、术语、数字、英文缩写 | Fun-ASR-Nano-2512 | `compare_asr_models.py`、`transcribe_audio.py --engine fun-asr-nano` | 本地 Nano 运行环境和模型缓存 |
| 4. 转写失败兜底 | 本地 FunASR 不可用时继续处理已有文本；需要字幕时间戳时可用 Whisper | Whisper，默认不使用低质量 `tiny/base/small` | `transcribe_audio.py --engine whisper` | 用户提供文本、已有转写稿 |
| 5. 预处理 | 清理长文本、识别发言人边界、抽取候选标的 | Codex/Skill Agent 所用大模型 | `process_transcript.py` | 原始转写、人工初审稿 |
| 6. 会议类型分发 | 按用户选择调用多人复盘、上市公司交流、专家交流或其他类型 skill | Codex/Skill Agent 所用大模型 | Dify Skill Agent、本仓库类型 skill | Dify 传入的 `meeting_type`、`meeting_series`、标题和正文 |
| 7. 名称和代码校对 | 校正公司名、股票代码、行业术语、人物/机构名、产品名 | Codex/Skill Agent 所用大模型 | `query_symbol_candidates.py`、`a-stock-data` 能力、review bridge 的 `/target-query` | A 股/HK/US 本地证券映射、公司资料、行情/标的证据 |
| 8. 专业证据核验 | 对不确定术语或专名做多路径确认 | Codex/Skill Agent 所用大模型 | 可用的网页/资料检索能力 | 官方公告、交易所披露、公司网站、监管/协会资料、行业报告、可靠财经新闻 |
| 9. 人工初审 | 用户先校对转写稿、分发言人和主题，确认后才允许进入正式整理 | 无 | `meeting_minutes_review_server.py`，`stage=pre_agent` | 用户人工修订 |
| 10. 生成纪要草稿 | 根据会议类型输出严格两段式 Markdown | Codex/Skill Agent 所用大模型 | 类型 skill、模板和格式校验脚本 | 初审后的转写稿、辅助转写、校对证据 |
| 11. 人工二审 | 用户在富文本页面确认发言人、标的、代码、数字和存疑项 | 无 | review server，`stage=post_agent` | 用户人工修订 |
| 12. 终稿导出和同步 | 生成 Markdown + Word，写入 Obsidian，生成后续结构化产物并同步知识库 | 无 | `export_to_obsidian.py`、`validate_word_export.py`、`sync_minutes_to_dify_dataset.py`、`sync_obsidian_to_gdrive.py` | Dify 会议纪要知识库、Google Drive 归档 |

## 转录规则

- 默认入口是 `scripts/transcribe_audio.py`。
- `--engine auto` 优先使用 SenseVoice/FunASR；本地不可用时才降级到 Whisper。
- SenseVoice 默认模型为 `iic/SenseVoiceSmall`，默认语言为 `zh`。
- 默认使用纯 SenseVoice 作为主转写和存疑时间戳来源，不强制挂 cam++ 或 VAD。
- `--output-format json|all` 会额外生成带时间锚点的 JSON；优先使用 SenseVoice 直接时间戳。
- cam++ 说话人分离和 `fsmn-vad` 只在显式需要区分发言人或分段时启用。
- 辅助模型保留为 `FunAudioLLM/Fun-ASR-Nano-2512`，用于对照校正公司名、金融术语、数字和英文缩写，不自动覆盖主转写。
- 需要区分发言人时使用 `--speaker-diarization`。
- 需要启用 SenseVoice VAD 分段时使用 `--sensevoice-vad`。
- 需要说话人分离失败即报错时使用 `--require-speaker-diarization`。
- 需要 `vtt`、`srt`、`tsv` 等字幕/时间戳格式时可显式使用 Whisper。
- 本仓库不打包模型权重或虚拟环境；部署环境应通过 `FUNASR_MODEL_CACHE`、`FUNASR_NANO_PYTHON` 等变量指向本地缓存和运行时。
- macOS 本地 Dify 转写桥可用 `scripts/start_sensevoice_transcription_server.sh` 启动；对应 LaunchAgent 模板在 `skills/投资会议纪要整理/launchagents/com.kumaai.sensevoice-transcription-server.plist`，会固定本地模型缓存和虚拟环境，避免每次整理会议纪要时重新下载模型。

## 整理和输出规则

通用规则：

- 先按真实发言顺序，再按发言人、板块/主题、标的拆分。
- 保留原发言人视角和人称，不把“我看好”“我们明天对接”改成第三人称总结。
- 不把长发言压缩成 1-3 句摘要；应拆成多个可读段落。
- 只删除无意义语气词、无意义重复和明显 ASR 噪声。
- 不编造催化、业绩数字、股票代码、客户名或结论。
- 所有存疑内容必须正文内联标注，并进入最终存疑表。

不同会议类型的输出差异：

- 多人复盘会：保持发言人切换和真实顺序，段落标题使用 `【板块｜标的(代码)】`。
- 上市公司交流：标题和元信息承载 `板块｜标的(代码)`，正文小段只写经营、订单、产能、毛利率、客户、风险等业务主题。
- 专家交流：使用问答形态，问题加粗，回答以 `【主题标签】` 开头，不写 `A:` 或 `A：`。
- 其他类型：保留用户自定义会议类型；如局部出现问答，按专家交流问答格式处理。

## 校对使用的数据和能力

股票代码和标的校验：

- 首选本地 `a-stock-data` 能力，尤其是 symbol lookup、resolve-targets、quote、stock-profile 等。
- 使用 `scripts/query_symbol_candidates.py` 查询本地 A 股、港股、美股和别名映射。
- A 股优先使用本地资源和 `.SH` / `.SZ` / `.BJ` 格式；中国投研语境默认先考虑 A 股，其次港股、美股。
- 只有结果能确认时才写入代码；候选冲突或找不到时保留原文并写入存疑。

行业术语和专有名词校验：

- 对行业术语、产品名、技术路线、政策/事件词、客户名、机构/人物名、财务术语等，不只依赖 ASR。
- 优先参考官方披露、公司网站、交易所文件、监管/协会资料、行业报告和可靠财经/新闻来源。
- 如果音频听感、上下文和外部证据无法统一，保留原始表述，正文加粗标注，并在存疑表列出候选解释。

## Dify 人工复核链路

在 Dify localhost 工作流中，必须经过两个人工关口：

1. 上传文件并填写会议标题、会议类型、会议系列。
2. 文本抽取或 SenseVoice 转写后，创建 `pre_agent` 初审草稿。
3. 用户在初审页面校对转写稿、发言人、分段、公司名、代码、数字和关键术语。
4. 初审确认后，Dify 以 `input_reviewed=true` 再次运行，才允许调用选定类型 skill。
5. skill 生成 `post_agent` 二审草稿。
6. 用户在富文本页面二审，确认存疑标注、正文和表格。
7. 二审确认后生成 `final.md` 和结构化摘要/标的表等后处理产物。
8. 只有用户点击归档确认后，才写入正式 Obsidian 目录、同步 Dify 知识库和 Google Drive。

未经确认的初始转写、模型草稿和二审前内容不得进入正式归档、Google Drive 或 Dify 知识库。

## 归档规则

原始材料归档：

- 归档根目录：`/Users/kumaai/Documents/Codex/workspace/投资纪要工作流/00 Inbox/会议原始记录`。
- 优先使用会议日期；未知时使用当前日期，格式为 `YYYY-MM-DD`。
- 每场会议单独建会话文件夹：`YYYY-MM-DD - 会议标题`。
- 原始文件命名为：`YYYY-MM-DD - 会议标题 - 原始NN-材料类型.扩展名`。
- 材料类型使用 `文稿`、`录音`、`录像`、`附件`。
- 同名冲突时保留所有文件，追加时间戳或数字后缀。
- 只复制原始文件，不删除或移动用户原文件。

终稿归档：

- 默认输出目录：`/Users/kumaai/Documents/Codex/workspace/投资纪要工作流/01 Projects/会议纪要/YYYY-MM-DD/`。
- 同名 Markdown 和 Word 文件放在会议日期目录下。
- 导出后同步整个 Obsidian 工作流目录到 `gdrive:投资纪要工作流存档/投资纪要工作流`。
- 终稿还会通过 `sync_minutes_to_dify_dataset.py` 写入 Dify `会议纪要整理知识库`。
- 如果 Word、Dify 或 Google Drive 同步失败，保留本地 Markdown/Word，报告失败原因，不删除本地结果。
- 清理历史输出时，只在明确要求下把旧文件移动到 `04 Archive/测试用`。

## 验证和回归

常用检查：

```bash
python3 skills/投资会议纪要整理/scripts/validate_utf8_text.py README.md --require-cjk
python3 skills/投资会议纪要整理/scripts/run_meeting_minutes_regression.py
python3 skills/投资会议纪要整理/scripts/validate_meeting_minutes_contract.py NOTE.md
python3 skills/投资会议纪要整理/scripts/validate_word_export.py NOTE.docx
python3 skills/投资会议纪要整理/scripts/transcribe_audio.py --check-model-cache
python3 skills/meeting-minutes-sanitizer/scripts/sanitize_minutes.py NOTE.md --output-dir outputs
```

包发布或迁移前，应确认：

- 所有 `SKILL.md` 保持 UTF-8 无 BOM、LF 换行。
- 中文文件名在压缩、传输和导入后没有乱码。
- 私有 API key、Dify token、本机日志、运行缓存、模型权重和虚拟环境没有进入仓库。
- 回归样例通过，默认输出仍符合两段式 contract。

## 不包含的内容

本仓库只保存可复用 skill、脚本、模板、样例和说明，不包含：

- 本机私有配置和 API key。
- Dify 私有 token 或数据集密钥。
- Google Drive/rclone 凭证。
- ASR 模型权重、下载缓存和 Python 虚拟环境。
- Obsidian 正式会议纪要、用户原始录音或转写原件。
- 临时草稿、运行日志和 `__pycache__`。

`skills/meeting-minutes-sanitizer` 的最小运行依赖见该目录下的 `requirements.txt`，当前只包含 Word 导出所需的 `python-docx`。

脚本中的本机路径是当前部署默认值。迁移到其他机器时，应把这些路径映射到目标环境的工作流根目录、模型缓存、Dify 地址、Obsidian vault 和 Google Drive 同步目标。
