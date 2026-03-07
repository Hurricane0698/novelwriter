
# CLAUDE.md


## Current Mode: Launch (since 2026-03-06)

Product is live with real users. Full rules: `.trellis/spec/guides/launch-mode.md`. Switch back to pre-launch only by CEO instruction "切换到预发布模式".

---

## Testing Guidelines
**Run tests via uv: `scripts/uv_run.sh pytest tests/`**
See `.trellis/spec/backend/python-environment-workflow.md` for full conventions.

## Coding Principles

1. **Confirmation > Ambiguity** — ask before implementing unclear requirements
2. **Reuse > Creation** — search codebase first; extend, don't duplicate
3. **Standards > Shortcuts** — follow established patterns and abstractions; but evaluate them first — existing convention may encode a wrong dependency direction or abstraction
4. **Minimalism > Completeness** — no hypothetical features; delete dead code
5. **Single Source of Truth** — tunable parameters live in exactly one spec file. Duplicated values across specs/comments drift and cause inconsistency. When adding or updating a parameter: put the exact value in the owning spec only; other docs get qualitative description + pointer (`See X § Y`); code comments reference the spec, never restate numbers. After updating, grep to confirm no stale copies: `rg -n "old_value" .trellis/spec/ app/ web/src/`

Removed components: see "Removed Components" table in `.trellis/spec/backend/index.md`.

## Design Decision Rules

These rules guide every feature/fix decision. When in doubt, apply them as filters. Full reasoning: `.trellis/spec/backend/world-model-architecture.md`.

1. **World model, not history** — new feature enriches the world model (entities/relationships/systems)? Yes → proceed. Tracks per-chapter events or history? No → reject.
2. **Better context, not more pipeline** — output quality poor? Improve context assembly (richer descriptions, better retrieval). Do NOT add LLM "reviewer"/"planner" nodes.
3. **User is the only author** — AI output is always a draft proposal. Never auto-commit to world model. Never let AI silently influence future generation.
4. **Ideas are disposable** — generation must be fast (fewer LLM calls = faster = more experimentation). If a feature slows generation, it must justify itself.
5. **Novel defines its own structure** — no genre categories, no hardcoded types. Schema is flexible; frontend renders by `display_type`, not by genre.
6. **Search, don't precompute** — world model stores structure (who, what, how they relate). Dynamic details live in chapter text, retrieved via RAG when needed.
7. **Simplicity = correct abstraction** — if two concepts can unify without losing expressiveness, they must unify. Redundant states and special cases mean we haven't found the right abstraction yet.
8. **Surface is a script, not a fact** — `surface` field = "everything the writer is allowed to see and use" (hints, atmosphere, phenomena). `truth` = the real answer (only checker sees). These are orthogonal to visibility.

## Collaboration (Intent Alignment)

- Restate goal, list assumptions, confirm before acting
- Make tradeoffs explicit; present 2-3 options when paths diverge
- Summarize what was done and what's pending after each step
