# PLAYBOOK — Ecommerce

## Customer support ticket
1. `mnemo_fact_get` the order/customer state before replying.
2. Recall any prior contact with this customer (`mnemo_recall`).
3. Draft a reply citing accurate availability/shipping/returns. Hold for approval
   if it involves a refund, cancellation, or exception to policy.

## Inventory sync
- When a new count arrives, `mnemo_fact_save` the stock level. If it contradicts
  a stored value, that's expected — the confidence ladder handles it. If a SKU is
  oversold, flag it immediately.

## Pricing / promo
1. Recall the outcome of past promos before proposing a new one.
2. Record the promo's parameters and, later, its result as a memory.

## Guardrails
- Never quote stock or a ship date you can't back with a current fact.
- Never state a price without a fact to source it.
- Refunds, cancellations, and policy exceptions need human approval.
