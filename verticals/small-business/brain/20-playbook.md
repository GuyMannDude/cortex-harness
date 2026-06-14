# PLAYBOOK — Small Business

## New customer
1. `mnemo_fact_save` the basics: name, contact, source, first request.
2. `mnemo_save` a one-line memory of the first interaction + any commitment.

## Quote / estimate
1. Recall prior quotes for similar work (`mnemo_recall`).
2. Apply stored pricing rules (`read_brain_file` → pricing if present).
3. Draft the quote, present it to {{vars.owner}} for approval before sending.

## Follow-up
- Each session, check for open commitments past their due date and surface them.
- Log the outcome of every follow-up as a memory so nothing is chased twice.

## End of day
- Summarize what changed (new customers, sent quotes, kept/broken promises).
- `session_end` to persist it.

## Guardrails
- Never quote a price you can't trace to a stored rule or owner instruction.
- Never confirm an appointment that conflicts with a known scheduling constraint.
