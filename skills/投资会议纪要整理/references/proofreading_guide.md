# 校对与名称判断

Use this file only when the transcript contains ASR noise, ambiguous names, abbreviations, company aliases, or unclear speaker names.

## Rules

- Judge the topic, sector, market, and speaker intent from context first.
- Correct obvious ASR noise only when the replacement is strongly supported by context.
- Match company full names, aliases, tickers, abbreviations, and industry terms through `symbol_sources.md` or `evidence_policy.md` when needed.
- Default Chinese investment meetings to A-share candidates unless the context clearly indicates HK, US, ADR, or another market.
- If the item cannot be confirmed, keep the source wording, mark it as doubtful, and use the ambiguity table.

## 发言人处理

- 优先结合上下文识别真实姓名。
- 如果无法确认，回退成 `发言人A`、`发言人B`、`发言人C`。
- 同一说话人名称前后不一致时，统一成一个最终名字，并在必要时写入存疑说明。

## 禁止事项

- 不要把原文改写成研报口吻。
- 不要补写没有出现过的盈利预测。
- 不要为了凑结构而虚构催化或风险。
