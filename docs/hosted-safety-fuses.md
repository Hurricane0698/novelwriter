# Hosted Safety Fuses

Pre-launch hosted mode now supports two simple safety fuses to reduce runaway cost risk:

- `HOSTED_MAX_USERS`: blocks creation of new hosted users once the active-user cap is reached.
- `AI_HARD_STOP_USD`: disables AI features once estimated hosted AI spend reaches the configured threshold.
- `AI_MANUAL_DISABLE=true`: immediate kill switch for all AI features while keeping login and non-AI pages available.

## Important limitation

`AI_HARD_STOP_USD` is based on **application-side token cost estimates**, not real-time Google Cloud Billing. Treat it as the primary in-app guardrail, and keep a safety buffer below your actual card risk threshold.

If you rely on custom Vertex/OpenAI-compatible pricing, set:

- `LLM_DEFAULT_INPUT_COST_PER_MILLION_USD`
- `LLM_DEFAULT_OUTPUT_COST_PER_MILLION_USD`

so the estimate matches your provider pricing more closely.

## Temporary P0 mitigation (not a full fix)

Hosted invite login still uses `invite_code + nickname` for account recovery/re-login. Until hosted auth is redesigned, treat the nickname as a **private high-entropy login name**, not a public display name.

- Use a long, hard-to-guess nickname/login name.
- Do **not** post it publicly in screenshots, group chats, or onboarding posts.
- This is only a temporary mitigation for pre-launch testing, not a permanent security fix.
