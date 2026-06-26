# Subagent Failure Policy

Subagent work is useful only when its limits are explicit. A failed or unavailable subagent must not be treated as a completed review.

## Failure Types

- Spawn unavailable.
- Spawn timeout.
- Invalid custom agent schema.
- Unusable or source-unsupported output.
- Findings contradict source material.
- The subagent tries to write final Markdown, Word, archive, or sync artifacts.
- The subagent attempts to spawn child agents.

## Required Handling

- State internally that the subagent was not usable; do not claim it passed.
- Do not write failure details into final Markdown.
- Do not skip existing human review gates.
- For high-risk source issues, preserve the unresolved item in `## 二、存疑与待确认` or report that human review is required.
- For low-risk tasks, single-writer fallback is allowed when formatting checks still pass.

## GO / NO-GO

Return `NO-GO` if:

- Any formatting or export validator fails.
- A formal note has unresolved high-severity source/draft conflicts that the user has not accepted.
- A subagent directly modifies final Markdown, Word, archive, or sync artifacts.

Return `GO` only when formatting validators pass and unresolved human-review items are absent or explicitly accepted by the user.
