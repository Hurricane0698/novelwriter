# SPDX-FileCopyrightText: 2026 Isaac.X.Ω.Yuan
# SPDX-License-Identifier: MIT

"""Japanese prompt templates."""

from __future__ import annotations

from app.core.text.catalog import PromptKey, register_templates

_TEMPLATES: dict[PromptKey, str] = {
    PromptKey.SYSTEM: """前の場面の言語、視点、語り口を引き継ぎ、まだ決着していない行動や選択の続きを書く。次の場面については <user_instruction> の作者の意図に従う。

<world_knowledge> にある呼び名、持ち物、約束と <narrative_constraints> の規則を守る。登場人物は自分が見聞きしたことや推測できることをもとに行動し、誤解も残り得る。作者が新たに指定した人物や場所は場面の中で自然に登場させる。

章題や解説を付けず、小説の本文だけを書く。""",

    PromptKey.CONTINUATION: """<novel_info>
タイトル：{title}
続きの章：{next_chapter_reference}
</novel_info>

{world_context}
{narrative_constraints}""",

    PromptKey.WORLD_GEN_SYSTEM: """作者の設定を、続きの執筆に役立つ草案にまとめる。鍵を持つ人物、貸し借り、秘密を知る人物、行動を制限する規則など、後の場面の描き方に影響する事実を選ぶ。成立条件は短く残し、噂には発言者を記す。根拠のない推測は加えない。該当する情報がなければ各配列は空でよい。""",

    PromptKey.WORLD_GEN: """原文から entities、relationships、systems を抽出する。名称は原文どおりにし、entity_type は Character、Location、Item、Faction などの英語で書く。関係には抽出済みの名前を source と target に指定し、具体的な label を付ける。
一緒に作用する規則を体系にまとめる。display_type は list、hierarchy、timeline のいずれか。items には label と description、階層には children、年表には time を使う。次の場面にかかわる制約を constraints に入れ、各事実は一度だけ記す。

原文 {chunk_directive}
{text}""",

    PromptKey.BOOTSTRAP_REFINEMENT: """小説の候補語から世界観のエンティティと関係を精査しています。
人物の選択や行動、その結果に影響する候補を優先する。同じ箇所に登場するだけでは関係の根拠にならない。

## 入力

候補語（名称: 出現ウィンドウ数）:
{candidate_lines}

共起ペア（名称A -- 名称B: 共起回数）:
{pair_lines}

## タスク

1) **ノイズ除去**: 動詞、形容詞、一般名詞などの非エンティティ語を除去する。
2) **別名統合**: 同一キャラクター/場所の異なる呼称を一つのエンティティに統合する。フルネームをnameとし、他をaliasesに入れる。
3) **分類**: entity_type は Character, Location, Item, Faction, Concept, other から選択。
4) **関係ラベル**: label は具体的で情報量のある説明（3-6文字）にする。「関連」「関係」などの曖昧な語は禁止。
5) 確信度の高いエンティティと関係のみを出力する。質を量より優先。

## 出力例

```json
{{
  "entities": [
    {{"name": "顧慎為", "entity_type": "Character", "aliases": ["顧兄", "小顧"]}},
    {{"name": "太玄宗", "entity_type": "Faction", "aliases": []}}
  ],
  "relationships": [
    {{"source_name": "顧慎為", "target_name": "太玄宗", "label": "弟子出身"}},
    {{"source_name": "独歩王", "target_name": "雨公子", "label": "父娘"}}
  ]
}}
```

完全なJSONを直接返してください。
""",
}

register_templates("ja", _TEMPLATES)
