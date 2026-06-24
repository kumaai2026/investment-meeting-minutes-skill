# Target Attribution Policy

This policy defines target roles, investment actions, recommendation signals, and heading coverage for the conditional Subagent workflow. Semantic attribution comes from the Content Integrity Reviewer or human gold labels; deterministic scripts only check consistency against `analysis_ledger.json`.

## Core Rules

- The first-mentioned or most frequently mentioned target is not automatically the primary target or recommendation target.
- Customers, suppliers, competitors, comparable companies, upstream/downstream entities, and background objects must not be promoted into recommendation targets without explicit source evidence.
- Negative actions are not recommendations, but their action object must still be recorded correctly.
- If the main discussion object and the action object differ, split the segment or include both in the heading.
- Main Orchestrator decides final segmentation and headings. Reviewers only return findings.

## Roles

Allowed roles are:

- `primary_target`
- `recommendation_target`
- `comparison_target`
- `customer`
- `supplier`
- `competitor`
- `upstream`
- `downstream`
- `industry_background`
- `incidental`
- `unclear`

## Explicit Recommendation

Recommendation means an explicit positive investment action, not merely a positive view.

Strong recommendation signals may set:

```json
{
  "roles": ["recommendation_target"],
  "action": "recommend",
  "explicit_recommendation": true
}
```

Strong signals include:

- 推荐
- 重点推荐
- 核心推荐
- 首选
- 第一选择
- 可以买
- 建议买入
- 准备买
- 准备加仓

## Weak Positive Or Tracking Language

Weak expressions must not automatically become recommendation targets:

- 建议关注
- 重点跟踪
- 弹性最大
- 空间较大
- 赔率不错
- 位置不错
- 值得重视
- 可以看看
- 有机会
- 短期催化

Depending on context, set:

- `action=positive`
- `action=watch`
- `action=trade_opportunity`

and set:

```json
{
  "explicit_recommendation": false
}
```

## Action Mapping

- “没有减仓”“继续拿着”: `action=hold`
- “减仓”: `action=reduce`
- “不建议追”“先回避”: `action=avoid`
- “看空”: `action=negative`
- Pure factual background: `action=neutral`
- Unclear source: `action=unclear`

## Heading Rules

- `primary_target_ids` should normally be included in `heading_target_ids`.
- `recommendation_target_ids` must be included in `heading_target_ids` unless `heading_exception_reason` is explicit and reviewable.
- A recommendation target should appear in the corresponding final heading.
- A customer, supplier, or comparison target must not be the only target in a heading when a recommendation target exists.
- `ticker_status` values other than `confirmed` must not appear as an unmarked confirmed code in the final heading.

## Split Rules

Split is required when:

- One semantic block contains two or more independent investment actions.
- Primary target and recommendation target differ and the heading cannot clearly cover both.
- Customer/supplier/competitor information is long enough to be mistaken for an investment target.
- The source first compares A, then explicitly recommends B.

Split may be skipped when:

- Multiple targets share one action and one logic chain.
- Targets are a basket or pair trade and the heading covers the basket.
- The source only lists tracking candidates without explicit action.

## Uncertainty

If attribution remains unclear:

- Keep source wording.
- Mark the target or action confidence as low.
- Add `unresolved_items`.
- Set top-level `requires_human_review=true`.
- Do not silently convert ambiguity into a confirmed title.
