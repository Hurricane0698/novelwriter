# SPDX-FileCopyrightText: 2026 Isaac.X.Ω.Yuan
# SPDX-License-Identifier: AGPL-3.0-only

"""Chinese prompt templates — the default catalog."""

from __future__ import annotations

from app.core.text.catalog import PromptKey, register_templates

_TEMPLATES: dict[PromptKey, str] = {
    PromptKey.SYSTEM: """接着前文写小说正文。沿用作品的语言、叙述视角和节奏，从上一场尚未解决的行动、选择或后果写起。遵循作者在 <user_instruction> 中对下一场的安排。

<world_knowledge> 记录与本场有关的设定。人物按自己见过、听过或能推断的信息行动，可以误解别人。保持已有称呼、物品归属、承诺和 <narrative_constraints> 中的规则一致。作者引入新人物或新地点时，让他们在场景中自然出现。

直接写故事，不加章节标题、提纲或创作说明。""",

    PromptKey.CONTINUATION: """<novel_info>
书名：{title}
待续章节：{next_chapter_reference}
</novel_info>

{world_context}
{narrative_constraints}""",

    PromptKey.WORLD_GEN_SYSTEM: """把作者提供的设定整理成供后续写作使用的草稿。留下会改变下一场写法的事实，例如谁拿着钥匙、谁欠谁什么、谁知道一个秘密、某条规则会阻止什么行动。用一句话保留事实成立的条件。传闻归于说话者；没有依据的推断留给作者。只要原文支持，三类条目都可以为空。""",

    PromptKey.WORLD_GEN: """从下文提取 entities、relationships 和 systems。实体沿用原名，entity_type 用 Character、Location、Item、Faction 等英文类别。关系用 source、target 指向已提取的实体，label 写清双方的具体关系。
体系只收录能一起使用的规则。display_type 为 list、hierarchy 或 timeline，items 用 label 和 description 表达具体内容，层级用 children，时间线用 time。constraints 放写下一场时需要遵守的规则。相同信息只记一次。

【设定原文】{chunk_directive}
{text}""",
    PromptKey.BOOTSTRAP_REFINEMENT: """你正在从一部小说的候选词中提炼出世界观实体和关系。
从原文支持的候选中优先留下会影响人物选择、行动或后果的设定。同现本身不能证明两者有关系。

## 输入

候选词（名称: 出现窗口数）:
{candidate_lines}

共现对（名称A -- 名称B: 共现次数）:
{pair_lines}

## 任务

1) **过滤噪声**: 去除动词、形容词、普通名词等非实体词（如「一声」「那个」「知道」）。
2) **合并别名**: 同一角色/地点的不同称呼合并为一个实体，全名为 name，其余放 aliases。例如：「顾慎为」和「顾兄」→ name=顾慎为, aliases=[顾兄]；「荷女」和「小荷」→ name=荷女, aliases=[小荷]。
3) **分类**: entity_type 从以下选择: Character, Location, Item, Faction, Organization, Concept, other。
4) **关系标签**: label 必须是具体且有信息量的描述（3-6字），能让读者一眼理解两者的关系。禁止使用「关联」「相关」「部属」等笼统词。好的例子: 父女、师徒、宿敌、青梅竹马、同门师兄弟、主仆、持有、坐落于、效忠于。坏的例子: 关联、相关、部属、关系。
5) **具体优先**: 优先保留更具体的专有名词，而不是上位泛词。若「炙皇星」和「皇星」同时出现，通常优先保留「炙皇星」；像「契师学院」「巫家药坊」这类带专名的学院/药坊/家族/军团/帝国/星球，通常应视为高价值实体。像「星际」「世界」这类宽泛背景词，除非明显是专名，否则不要保留。
6) 只输出确信度高的实体和关系，宁缺毋滥。

## 示例输出片段

```json
{{
  "entities": [
    {{"name": "顾慎为", "entity_type": "Character", "aliases": ["顾兄", "小顾"]}},
    {{"name": "太玄宗", "entity_type": "Faction", "aliases": []}}
  ],
  "relationships": [
    {{"source_name": "顾慎为", "target_name": "太玄宗", "label": "弟子出身"}},
    {{"source_name": "独步王", "target_name": "雨公子", "label": "父女"}}
  ]
}}
```

请直接返回完整 JSON。
""",
}

register_templates("zh", _TEMPLATES)
