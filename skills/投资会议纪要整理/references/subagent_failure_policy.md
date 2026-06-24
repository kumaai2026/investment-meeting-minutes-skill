# Subagent Failure Policy

Subagent review is useful only when its status is explicit and auditable. A failed or unavailable subagent must not be treated as a pass.

## Failure Types

- Spawn unavailable.
- Spawn timeout.
- Invalid custom agent schema.
- Invalid JSON output.
- Missing required fields.
- Reviewer result contradicts source material.
- Reviewer tries to write final Markdown, Word, archive, or sync artifacts.
- Reviewer attempts to spawn child agents.

## Required Handling

- Record the failure in `qa_report.json`.
- Set `subagent_status` for the failed reviewer to `fail`, `unavailable`, `restart_required`, or `not_run`.
- Do not write failure details into final Markdown.
- Do not skip existing human review gates.
- For high-risk tasks, set `requires_human_review=true`.
- For low-risk tasks, a single-agent fallback is allowed only when validators still pass.

## GO / NO-GO

Return `NO-GO` if:

- Any hard validator fails.
- `qa_report.go_status` is `go` while a check failed.
- A formal note has unresolved high-severity post-draft findings.
- A subagent can modify final Markdown, Word, archive, or sync artifacts.
- Dify subagent support is claimed without live evidence.

Return `GO` only when deterministic validators pass and unresolved human-review items are absent or explicitly accepted by the user.
