# SPDX-FileCopyrightText: 2026 Isaac.X.Ω.Yuan
# SPDX-License-Identifier: MIT

"""English prompt templates."""

from __future__ import annotations

from app.core.text.catalog import PromptKey, register_templates

_TEMPLATES: dict[PromptKey, str] = {
    PromptKey.SYSTEM: """Continue the novel in the language, point of view and cadence of the preceding scene. Pick up an unfinished action, choice or consequence. Follow the author's direction for the next scene in <user_instruction>.

Use <world_knowledge> to preserve names, possession, commitments and the rules in <narrative_constraints>. Characters act on what they have seen, heard or can infer, including mistaken beliefs. Introduce a new person or place naturally when the author calls for it.

Return story prose, without a chapter heading or editorial notes.""",

    PromptKey.CONTINUATION: """<novel_info>
Title: {title}
Chapter to continue: {next_chapter_reference}
</novel_info>

{world_context}
{narrative_constraints}""",

    PromptKey.WORLD_GEN_SYSTEM: """Extract a draft world model that a writer can use in later scenes. Keep facts whose omission could change the writing: who holds a key, owes a favor, knows a secret, or is constrained by a rule. Preserve the conditions of each fact in a short phrase. Attribute rumors to the speaker. Leave unsupported inferences to the author. Any of the three collections can be empty.""",

    PromptKey.WORLD_GEN: """Extract entities, relationships and systems from the source. Use the original names and concise English entity_type values such as Character, Location, Item or Faction. Relationships use source and target names from the extracted entities and a specific label.
Group rules that operate together in a system. Choose list, hierarchy or timeline for display_type. Items use label and description, with children for nesting or time for dated entries. Put rules that affect the next scene in constraints. Record each fact once.

Source {chunk_directive}
{text}""",

    PromptKey.BOOTSTRAP_REFINEMENT: """You are refining candidate terms from a novel into world-building entities and relationships.
Keep candidates that affect choices, actions or consequences. Co-occurrence alone does not establish a relationship.

## Input

Candidate terms (name: window count):
{candidate_lines}

Co-occurrence pairs (Name A -- Name B: co-occurrence count):
{pair_lines}

## Task

1) **Filter noise**: Remove verbs, adjectives, common nouns, and other non-entity words.
2) **Merge aliases**: Combine different references to the same character/location into one entity — use the full name as `name`, put alternatives in `aliases`. For example: "John" and "Mr. Smith" → name=John Smith, aliases=[John, Mr. Smith].
3) **Classify**: entity_type from: Character, Location, Item, Faction, Organization, Concept, other.
4) **Relationship labels**: label must be a specific, informative description (2-4 words) that conveys the relationship at a glance. Do NOT use vague words like "related", "associated", "connected". Good examples: father-daughter, mentor-student, sworn enemy, childhood friend, master-servant, belongs to, located in, loyal to. Bad examples: related, associated, connected, linked.
5) **Prefer concrete names**: prefer the more specific proper noun over a generic umbrella term. If both a concrete place/org name and a broad background noun appear, usually keep the concrete one. School / shop / clan / legion / empire / planet-style names with a distinctive prefix are usually high-value entities; broad backdrop words like "interstellar" or "world" are usually not.
6) Only output high-confidence entities and relationships — quality over quantity.

## Example output

```json
{{
  "entities": [
    {{"name": "John Smith", "entity_type": "Character", "aliases": ["John", "Commander Smith"]}},
    {{"name": "The Order", "entity_type": "Faction", "aliases": []}}
  ],
  "relationships": [
    {{"source_name": "John Smith", "target_name": "The Order", "label": "founding member"}},
    {{"source_name": "Lord Blackwood", "target_name": "Eleanor", "label": "father-daughter"}}
  ]
}}
```

Return the complete JSON directly.
""",
}

register_templates("en", _TEMPLATES)
