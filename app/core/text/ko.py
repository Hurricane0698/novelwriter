# SPDX-FileCopyrightText: 2026 Isaac.X.Ω.Yuan
# SPDX-License-Identifier: AGPL-3.0-only

"""Korean prompt templates."""

from __future__ import annotations

from app.core.text.catalog import PromptKey, register_templates

_TEMPLATES: dict[PromptKey, str] = {
    PromptKey.SYSTEM: """앞 장면의 언어와 시점, 문체를 이어 소설 본문을 쓴다. 마무리되지 않은 행동이나 선택, 그 결과에서 시작한다. 다음 장면에 관한 작가의 <user_instruction>을 따른다.

<world_knowledge>에 나오는 이름, 소지품, 약속과 <narrative_constraints>의 규칙을 지킨다. 인물은 자신이 보거나 듣거나 추론할 수 있는 정보에 따라 행동하며 오해할 수도 있다. 작가가 새 인물이나 장소를 제시하면 장면 안에서 자연스럽게 소개한다.

장 제목이나 해설 없이 소설 본문만 쓴다.""",

    PromptKey.CONTINUATION: """<novel_info>
제목: {title}
이어쓰기 장: {next_chapter_reference}
</novel_info>

{world_context}
{narrative_constraints}""",

    PromptKey.WORLD_GEN_SYSTEM: """작가가 준 설정을 후속 집필에 쓸 초안으로 정리한다. 열쇠를 가진 사람, 갚아야 할 빚, 비밀을 아는 사람, 행동을 제약하는 규칙처럼 다음 장면에 영향을 줄 사실을 남긴다. 사실이 성립하는 조건을 짧게 적고 소문에는 발화자를 명시한다. 근거 없는 추론은 보태지 않는다. 해당하는 사실이 없으면 각 배열은 비워 둔다.""",

    PromptKey.WORLD_GEN: """원문에서 entities, relationships, systems를 추출한다. 원래 이름을 쓰고 entity_type은 Character, Location, Item, Faction 같은 영어 분류로 적는다. 관계의 source와 target은 추출한 이름을 사용하고 label에 구체적인 관계를 적는다.
함께 작동하는 규칙을 하나의 체계로 묶는다. display_type은 list, hierarchy, timeline 중에서 고른다. items에는 label과 description, 계층에는 children, 연표에는 time을 쓴다. 다음 장면에 영향을 주는 제약을 constraints에 넣고 같은 사실은 한 번만 기록한다.

원문 {chunk_directive}
{text}""",

    PromptKey.BOOTSTRAP_REFINEMENT: """소설의 후보 단어에서 세계관 엔티티와 관계를 정제하고 있습니다.
인물의 선택, 행동과 결과에 영향을 주는 후보를 우선한다. 함께 등장했다는 사실만으로 관계를 단정하지 않는다.

## 입력

후보 단어(이름: 출현 윈도우 수):
{candidate_lines}

공기 쌍(이름A -- 이름B: 공기 횟수):
{pair_lines}

## 작업

1) **노이즈 제거**: 동사, 형용사, 일반 명사 등 비엔티티 단어를 제거.
2) **별명 통합**: 같은 캐릭터/장소의 다른 호칭을 하나의 엔티티로 통합. 전체 이름을 name으로, 나머지를 aliases에.
3) **분류**: entity_type은 Character, Location, Item, Faction, Concept, other 중 선택.
4) **관계 라벨**: label은 구체적이고 정보가 풍부한 설명(3-6글자). "관련", "관계" 같은 모호한 단어 금지.
5) 확신도 높은 엔티티와 관계만 출력. 질을 양보다 우선.

## 출력 예시

```json
{{
  "entities": [
    {{"name": "고신위", "entity_type": "Character", "aliases": ["고형", "소고"]}},
    {{"name": "태현종", "entity_type": "Faction", "aliases": []}}
  ],
  "relationships": [
    {{"source_name": "고신위", "target_name": "태현종", "label": "제자 출신"}},
    {{"source_name": "독보왕", "target_name": "우공자", "label": "부녀"}}
  ]
}}
```

완전한 JSON을 직접 반환해 주세요.
""",
}

register_templates("ko", _TEMPLATES)
