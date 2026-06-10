# 标的代码来源

## 结论

- `LondonMarket/Global-Stock-Symbols` 适合补充全球市场，尤其是 US/HK 等数据。
- 该仓库不包含主流 A 股 `.SH` / `.SZ` / `.BJ` 代码清单，因此不能单独作为中文投资会议的股票代码主数据源。

## 本地资源目录

使用以下目录作为本地主数据缓存：

`/Users/kumaai/Documents/Codex/workspace/投资纪要工作流/03 Resources`

建议优先读取：
- `market-symbols/a_share_list.csv`
- `market-symbols/global-stock-symbols-source/`
- `market-symbols/README.md`

## 推荐使用顺序

1. A 股：本地 A 股清单
2. 港股 / 美股 / 其他：`Global-Stock-Symbols`
3. 本地资源缺失时：刷新资源后再补注代码

## 刷新建议

- A 股资源优先使用维护活跃的开源项目或官方交易所来源。
- 全球资源可重新同步 `LondonMarket/Global-Stock-Symbols`。
