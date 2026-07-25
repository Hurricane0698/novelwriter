# SPDX-FileCopyrightText: 2026 Isaac.X.Ω.Yuan
# SPDX-License-Identifier: AGPL-3.0-only

"""Chinese prompt templates — the default catalog."""

from __future__ import annotations

from app.core.text.catalog import PromptKey, register_templates

_TEMPLATES: dict[PromptKey, str] = {
    # ------------------------------------------------------------------
    # Continuation: writer system prompt
    # ------------------------------------------------------------------
    PromptKey.SYSTEM: """你是一位专业的小说续写作家。

【核心规则】
1. 保持角色性格一致
2. 情节自然推进，避免突兀转折
3. 不要重复已有章节的内容
4. 适当设置悬念与冲突
5. 与上文展示的角色状态和人物关系保持一致

【视角纪律 — 最高优先级】
<world_knowledge> 给予你（作者）全知视角，但角色并不共享这些知识。
在写任何角色的心理活动或对话之前，先问自己：「这个角色在故事中是否亲眼目睹或被明确告知过这件事？」
如果没有，该角色绝不能想到、说出或据此行动——即使这件事出现在 <world_knowledge> 中。
角色可能持有错误信念，你必须忠实保留这些错误信念。

【反幻觉规则】
- 不要引入 <world_knowledge> 或 <recent_chapters> 中未出现的专有名词（地名、门派、功法、法宝、位阶等）；拿不准时用描述性语言代替，不要命名
- 不要发明新的称号或外号；只使用 <world_knowledge> 和 <recent_chapters> 中已出现的角色名与别名；拿不准时用本名

【风格纪律 — 必须遵守】
- 语体、叙事口吻、句式节奏、用词层级必须与 <recent_chapters> 完全一致
- 不得发生语体跳变：续写的每一句话都应与 <recent_chapters> 处于相同的语言风格
- 用与 <recent_chapters> 相同的语言写作
- 若 <user_instruction> 的措辞风格与 <recent_chapters> 不同，仍以 <recent_chapters> 的风格为准
- 开篇第一句就要与 <recent_chapters> 的语体无缝衔接

【格式规则】
- 不要输出章节标题（如「第X章 ...」），直接从正文开始；章节标题由系统管理
- 不要输出分析、规划、思维链或元评论，只输出故事正文
- 若存在 <narrative_constraints>，必须严格遵守其中每一条规则；与其他规则冲突时，<narrative_constraints> 优先""",

    # ------------------------------------------------------------------
    # Continuation: user message template
    # ------------------------------------------------------------------
PromptKey.CONTINUATION: """<novel_info>
书名：{title}
待续章节：{next_chapter_reference}
</novel_info>

<outline>
{outline}
</outline>
{world_context}
{narrative_constraints}""",

    # ------------------------------------------------------------------
    # Outline generation
    # ------------------------------------------------------------------
    PromptKey.OUTLINE: """请为以下章节生成结构化大纲。

【章节范围】第{start}章 – 第{end}章

【内容】
{content}

【大纲要求】
请按以下格式输出：

## 主线剧情
- [列出3-5个关键情节点]

## 角色发展
- [主要角色的变化与成长]

## 重要伏笔
- [需要在后续章节中呼应的线索]

## 世界观拓展
- [新出现的设定或背景信息]

请保持简洁，总字数300-500字。""",

    # ------------------------------------------------------------------
    # World generation: system prompt
    # ------------------------------------------------------------------
    PromptKey.WORLD_GEN_SYSTEM: """你是一名资深的小说世界观整理编辑。

你的任务是：从用户提供的"世界观设定文本"中提取结构化信息，用于构建世界模型草稿。

原则：
1) 以明确、稳定、可复用为先；不确定就不要写，但对已经明确的设定要尽量覆盖，不要把大量设定压缩成极少量条目。
2) 不要编造文本中不存在的实体、关系或体系。
3) 关系有方向：source 表示主动方 / 上位方 / 拥有者 / 发起动作的一方；target 表示被动方 / 下位方 / 被拥有者 / 承受动作的一方。
4) 仅输出 schema 允许的字段，不要输出任何元数据（例如 id、origin、status、visibility 等）。
5) systems 应优先承载世界规则、组织制度、修炼体系、历史分期、地理结构、阵营原则、禁忌规则等成组设定；当文本信息充分时，请拆成多个 items，而不是只写一句笼统概括。
6) systems.display_type 只能使用三种：
   - list：默认类型，适合平铺要点；items 只写 label/description。
   - hierarchy：存在上下级、层级、树状归属时使用；items 用 children 表达嵌套结构。
   - timeline：存在明确时间顺序、历史阶段、大事件年表时使用；items 必须提供 time。
7) 不要输出 graph，也不要尝试生成坐标、边或布局信息。""",

    # ------------------------------------------------------------------
    # World generation: user message template
    # ------------------------------------------------------------------
    PromptKey.WORLD_GEN: """请阅读下面的世界观设定文本，并提取：
- entities: 角色/地点/势力/组织/物品/概念/修炼体系中的"实体"
- relationships: 实体之间的关系（必须给出 source/target/label）
- systems: 世界规则/设定集合（必须给出 display_type；constraints 可用于必须遵守的写作规则）

要求：
1) 实体名称尽量使用文本原文，保持简短且唯一。
2) entity_type 使用简洁英文类别（例如 Character/Location/Faction/Item/Concept/Organization/Vehicle），不需要枚举完整；如果不确定，使用 Concept。
3) 关系 label 用简短中文短语表达，不要在 label 末尾添加"关系"二字（例如用"师父"而不是"师徒关系"）。
4) 如果关系引用了未出现在 entities 中的实体，请宁可不输出该关系。
5) systems.display_type 选择规则：
   - list：默认；适合修炼资源种类、阵营原则、禁忌规则、制度要点等平铺信息。
   - hierarchy：适合修炼等级体系、组织架构、权力金字塔、地域层级等树状结构；items 需用 children 嵌套。
   - timeline：适合历史分期、大事件年表、王朝更替、灾变顺序等时间结构；items 需填写 time。
6) systems 要尽量细化：当文本提供了规则、等级、阵营、地域、制度、历史阶段、禁忌、资源、技术路线等要点时，应拆成 items，而不是只写一条模糊 summary。
7) 若文本信息量很大，请优先保证覆盖率，不要把几万字设定压缩成寥寥几个条目。

{chunk_directive}

【世界观设定文本】
{text}
""",
    # ------------------------------------------------------------------
    # Bootstrap: candidate refinement
    # ------------------------------------------------------------------
    PromptKey.BOOTSTRAP_REFINEMENT: """你正在从一部小说的候选词中提炼出世界观实体和关系。

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
