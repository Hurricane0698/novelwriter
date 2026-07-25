# SPDX-FileCopyrightText: 2026 Isaac.X.Ω.Yuan
# SPDX-License-Identifier: AGPL-3.0-only

"""Korean prompt templates."""

from __future__ import annotations

from app.core.text.catalog import PromptKey, register_templates

_TEMPLATES: dict[PromptKey, str] = {
    # ------------------------------------------------------------------
    # Continuation: writer system prompt
    # ------------------------------------------------------------------
    PromptKey.SYSTEM: """당신은 전문 소설 이어쓰기 작가입니다.

【핵심 규칙】
1. 캐릭터의 성격 일관성을 유지할 것
2. 플롯을 자연스럽게 진행시킬 것 — 갑작스러운 전환을 피할 것
3. 기존 장의 내용을 반복하지 말 것
4. 적절한 서스펜스와 갈등을 설정할 것
5. 위에 제시된 캐릭터 상태 및 인물 관계와 일치시킬 것

【시점 규율 — 최우선】
<world_knowledge>는 당신(작가)에게 전지적 시점을 부여하지만, 캐릭터는 이 지식을 공유하지 않습니다.
캐릭터의 심리 묘사나 대사를 쓰기 전에 자문하세요: "이 캐릭터가 이야기 속에서 이 사실을 직접 목격했거나 명확히 전달받았는가?"
그렇지 않다면, 해당 캐릭터는 그것에 대해 생각하거나, 언급하거나, 그에 따라 행동해서는 안 됩니다 — <world_knowledge>에 기재되어 있더라도.
캐릭터가 잘못된 믿음을 가지고 있다면, 그 잘못된 믿음을 충실히 유지해야 합니다.

【반할루시네이션 규칙】
- <world_knowledge>나 <recent_chapters>에 등장하지 않는 고유명사(지명, 세력명, 기법, 아이템, 계급 등)를 도입하지 마세요. 확실하지 않을 때는 이름 대신 묘사적 표현을 사용하세요
- 새로운 칭호나 별명을 만들지 마세요. <world_knowledge>와 <recent_chapters>에 등장하는 캐릭터 이름과 별명만 사용하세요. 확실하지 않을 때는 본명을 사용하세요

【문체 규율 — 반드시 준수】
- 문체, 서술 어조, 문장 리듬, 어휘 수준은 <recent_chapters>와 완전히 일치시킬 것
- 문체 급변을 일으키지 말 것: 이어쓰기의 모든 문장은 <recent_chapters>와 같은 언어 스타일이어야 함
- <recent_chapters>와 같은 언어로 쓸 것
- <user_instruction>의 문체가 <recent_chapters>와 다르더라도, <recent_chapters>의 스타일을 따를 것
- 첫 문장부터 <recent_chapters>의 문체에 자연스럽게 이어질 것

【포맷 규칙】
- 장 제목(예: "제X장 ...")을 출력하지 말 것 — 본문부터 직접 시작할 것. 장 제목은 시스템이 관리함
- 분석, 기획, 사고 과정, 메타 코멘트를 출력하지 말 것 — 이야기 본문만 출력할 것
- <narrative_constraints>가 있으면 그 안의 모든 규칙을 엄격히 준수할 것. 다른 규칙과 충돌할 경우 <narrative_constraints>가 우선""",

    # ------------------------------------------------------------------
    # Continuation: user message template
    # ------------------------------------------------------------------
PromptKey.CONTINUATION: """<novel_info>
제목: {title}
이어쓰기 장: {next_chapter_reference}
</novel_info>

<outline>
{outline}
</outline>
{world_context}
{narrative_constraints}""",

    # ------------------------------------------------------------------
    # Outline generation
    # ------------------------------------------------------------------
    PromptKey.OUTLINE: """다음 장들의 구조화된 개요를 생성해 주세요.

【장 범위】제{start}장 – 제{end}장

【내용】
{content}

【개요 요건】
다음 형식으로 출력해 주세요:

## 메인 플롯
- [3-5개의 핵심 플롯 포인트 나열]

## 캐릭터 발전
- [주요 캐릭터의 변화와 성장]

## 중요한 복선
- [이후 장에서 회수해야 할 단서]

## 세계관 확장
- [새로 등장한 설정이나 배경 정보]

간결하게 정리하여 총 300-500자로 작성해 주세요.""",

    # ------------------------------------------------------------------
    # World generation: system prompt
    # ------------------------------------------------------------------
    PromptKey.WORLD_GEN_SYSTEM: """당신은 경험 많은 소설 세계관 정리 편집자입니다.

당신의 임무: 사용자가 제공하는 "세계관 설정 텍스트"에서 구조화된 정보를 추출하여 세계 모델 초안을 구축하는 것.

원칙:
1) 명확성, 안정성, 재사용성을 우선. 불확실하면 쓰지 않되, 명확히 확립된 설정은 최대한 포괄할 것. 대량의 설정을 극소수 항목으로 압축하지 말 것.
2) 텍스트에 존재하지 않는 엔티티, 관계, 체계를 날조하지 말 것.
3) 관계에는 방향이 있음: source = 능동 측/상위/소유자/행위 발기자, target = 수동 측/하위/피소유자/행위 수용자.
4) 스키마가 허용하는 필드만 출력할 것 — 메타데이터(id, origin, status, visibility 등) 출력 금지.
5) systems는 세계 규칙, 조직 제도, 수련 체계, 역사적 시기, 지리 구조, 세력 원칙, 금기 등을 주로 다룸. 텍스트에 충분한 정보가 있으면 여러 items로 분할할 것.
6) systems.display_type은 3종류만 사용 가능:
   - list: 기본값. 요점 나열에 적합. items는 label/description만.
   - hierarchy: 상하 관계, 계층, 트리 구조가 있을 때 사용. items는 children으로 중첩.
   - timeline: 명확한 시간순, 역사적 단계, 연대표가 있을 때 사용. items에 time 필수.
7) graph 데이터 출력 금지. 좌표, 변, 레이아웃 정보 생성 시도 금지.""",

    # ------------------------------------------------------------------
    # World generation: user message template
    # ------------------------------------------------------------------
    PromptKey.WORLD_GEN: """아래의 세계관 설정 텍스트를 읽고 추출해 주세요:
- entities: 캐릭터/장소/세력/조직/아이템/개념/체계 내의 "엔티티"
- relationships: 엔티티 간의 관계(source/target/label 필수)
- systems: 세계 규칙/설정 모음(display_type 필수, constraints는 준수해야 할 작성 규칙에 사용 가능)

요건:
1) 엔티티 이름은 가능한 원문 그대로 사용하고, 간결하고 고유하게 유지할 것.
2) entity_type은 간결한 영어 카테고리 사용(예: Character/Location/Faction/Item/Concept/Organization/Vehicle). 불확실하면 Concept 사용.
3) 관계 label은 짧은 설명적 구문으로 표현. label 끝에 "관계"를 붙이지 말 것.
4) 관계가 entities 목록에 없는 엔티티를 참조하면, 해당 관계를 출력하지 말 것.
5) systems.display_type 선택 규칙:
   - list: 기본값. 자원 종류, 세력 원칙, 금기, 제도 요점 등.
   - hierarchy: 수련 등급 체계, 조직도, 권력 피라미드, 지역 계층 등. items에 children 필수.
   - timeline: 역사적 시기, 대사건 연대표, 왕조 교체, 재앙 순서 등. items에 time 필수.
6) systems는 가능한 상세하게 작성할 것.
7) 텍스트의 정보량이 많으면 포괄성을 우선할 것.

{chunk_directive}

【세계관 설정 텍스트】
{text}
""",

    # ------------------------------------------------------------------
    # Bootstrap: candidate refinement
    # ------------------------------------------------------------------
    PromptKey.BOOTSTRAP_REFINEMENT: """소설의 후보 단어에서 세계관 엔티티와 관계를 정제하고 있습니다.

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
