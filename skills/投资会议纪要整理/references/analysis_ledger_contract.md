# Analysis Ledger Contract

The analysis ledger is the single internal planning artifact for conditional Subagent review. It replaces the old multi-sidecar chain. It is not a final note and must not be copied into Markdown, Word, archive, Google Drive, Dify knowledge base, or sanitizer RAG outputs.

## Top Level

```json
{
  "artifact_type": "investment_meeting_analysis_ledger",
  "artifact_version": "subagent.v1",
  "source_id": "",
  "source_hash": "",
  "status": "draft",
  "warnings": [],
  "requires_human_review": false,
  "source_profile": {},
  "transcript_audit": {
    "status": "not_required",
    "findings": []
  },
  "segments": [],
  "post_draft_review": {
    "status": "not_run",
    "findings": []
  }
}
```

Allowed top-level status values:

- `draft`
- `reviewed`
- `needs_review`
- `blocked`

## Segment

```json
{
  "segment_id": "seg-001",
  "speaker_ref": "",
  "source_ref": "",
  "source_span": "",
  "topic": "",
  "pure_topic": false,
  "targets": [],
  "primary_target_ids": [],
  "recommendation_target_ids": [],
  "heading_target_ids": [],
  "suggested_heading": "",
  "final_heading": "",
  "split_required": false,
  "heading_exception_reason": "",
  "high_risk_claims": [],
  "unresolved_items": []
}
```

`segment_id` values must be unique. Any id in `primary_target_ids`, `recommendation_target_ids`, and `heading_target_ids` must exist in the same segment's `targets`.

If `unresolved_items` is non-empty, top-level `requires_human_review` must be `true`.

## Target

```json
{
  "target_id": "target-001",
  "display_name": "",
  "ticker": null,
  "ticker_status": "confirmed",
  "roles": ["primary_target"],
  "action": "recommend",
  "stance": "positive",
  "explicit_recommendation": true,
  "source_ref": "",
  "evidence_span": "",
  "confidence": "high"
}
```

Allowed roles:

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

Allowed actions:

- `recommend`
- `positive`
- `hold`
- `watch`
- `trade_opportunity`
- `reduce`
- `avoid`
- `negative`
- `neutral`
- `unclear`

Allowed stance values:

- `positive`
- `neutral`
- `negative`
- `mixed`
- `unclear`

Allowed ticker status values:

- `confirmed`
- `candidate_only`
- `unverified`
- `not_found`
- `not_applicable`

Recommendation targets must:

- Appear in `recommendation_target_ids`.
- Include the `recommendation_target` role.
- Set `explicit_recommendation=true`.
- Include `evidence_span`.
- Include `confidence`.

`ticker_status` values other than `confirmed` must not be treated as confirmed stock codes in final headings.

## High-Risk Claim

```json
{
  "claim_id": "",
  "claim_type": "",
  "claim_text": "",
  "source_ref": "",
  "source_evidence": "",
  "external_verification_path": "",
  "evidence_status": "",
  "final_handling": ""
}
```

High-risk claims include company names, tickers, customers, suppliers, competitors, orders, capacity, price, profit, revenue, gross margin, valuation, market cap, dates, policies, product models, technical terms, and investment actions.

## QA Report

`qa_report.json` must contain:

- `checks`
- `go_status`
- `no_go_reasons`
- `requires_human_review`
- `subagent_status`

If any hard check fails, `go_status` must not be `go`.
