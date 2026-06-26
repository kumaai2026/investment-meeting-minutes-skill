# 股票代码来源

Use this file only when a company name, alias, ticker, or market suffix needs confirmation.

## Source Order

1. `a-stock-data` live sources when available.
2. Local A-share table under the workflow resources.
3. Local global-symbol table for HK/US/other markets.
4. Official exchange, company announcement, company website, or other professional source when local candidates are insufficient.

## 本地资源目录

Local symbol cache:

`/Users/kumaai/Documents/Codex/workspace/投资纪要工作流/03 Resources`

Useful paths:
- `market-symbols/a_share_list.csv`
- `market-symbols/global-stock-symbols-source/`
- `market-symbols/README.md`

## Rules

- Do not write an unconfirmed ticker as a confirmed heading code.
- Local symbol candidates are not final proof when multiple candidates match.
- If market context is unclear, prefer preserving the source wording and adding a doubtful item.
- Refresh local resources as a deployment task, not during final note writing.
