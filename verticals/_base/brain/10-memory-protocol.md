# MEMORY PROTOCOL

A short ritual that makes every cold start feel warm. Adapted from the Mnemo
Cortex "Lane Protocol."

## At session start
1. Call `agent_startup` once — loads your brain lanes + recent memory.
2. Skim what came back before doing anything else.

## During work
3. **Recall before you act.** Use `mnemo_recall` for context, `mnemo_fact_get`
   for exact values (names, prices, IDs, settings). Don't re-derive what you
   already know.
4. **Prefer facts over prose** for anything key-value. "What's the customer's
   plan tier?" is a fact lookup, not a search.

## When you learn something
5. **Save the distilled version, not the transcript.** A decision, an outcome, a
   stated preference — one clean sentence with the why. Use `mnemo_save`.
6. **Assert concrete attributes as facts** with `mnemo_fact_save`. New evidence
   sharpens confidence over time.

## At session end
7. Call `session_end` (if enabled) so the next session starts informed.

## Never
- Never invent a fact to fill a gap. If you don't know, say so or look it up.
- Never store secrets (full card numbers, passwords, API keys) in memory.
