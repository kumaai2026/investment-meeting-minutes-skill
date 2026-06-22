# Sidecar 隐私规则

本文件定义 MAS sidecar 的隐私边界。

## sidecar 类型

### internal_sidecar

用途：
- 调试
- 人工校对
- 红队复核
- 回归测试

可以包含：
- source refs
- source span 摘要
- 本地文件名或相对引用
- 低置信词
- 证据路径摘要
- 未确认客户名或术语候选

限制：
- 不写入最终 Markdown/Word。
- 不同步到公开知识库。
- 不作为 RAG 入库文本直接使用。

### rag_sidecar

用途：
- 下游 RAG 入库
- 检索增强
- 非发言人导向的知识整理

必须脱敏：
- 不包含真实发言人姓名、身份、机构、个人风格。
- 不包含内部绝对路径。
- 不包含 review URL、draft ID、history URL、token、cookie、API key。
- 不包含未脱敏客户名，除非客户名已经在最终确认纪要中允许公开。
- 不包含逐字 source span 或原始音频片段路径。

## forbidden keys

`rag_sidecar` 中禁止出现：
- `speaker_name`
- `speaker_identity`
- `speaker_affiliation`
- `speaker_style`
- `raw_source_path`
- `absolute_path`
- `review_url`
- `draft_id`
- `history_url`
- `api_key`
- `token`
- `cookie`
- `source_span`
- `raw_transcript`
- `internal_notes`

## 终稿隔离

最终 Markdown/Word 既不是 internal_sidecar，也不是 rag_sidecar。终稿只能保留读者需要的会议内容、元信息、近原文整理和存疑表。

如果需要 RAG 入库，应在人工确认后使用脱敏或结构化后处理脚本生成独立产物。
