// SPDX-FileCopyrightText: 2026 Isaac.X.Ω.Yuan
// SPDX-License-Identifier: AGPL-3.0-only

/**
 * Static subset of the public-domain Journey to the West worldpack used by the
 * landing lattice stage. Source: `data/worldpacks/journey-to-the-west.json`
 * (CC0 / public-domain novel text). Coordinates are hand-placed in stage UV
 * space so DOM labels and shader knots stay aligned.
 */

export type LatticeEntityType = 'character' | 'location' | 'item' | 'faction'

export type LatticeEntity = {
  id: string
  name: string
  type: LatticeEntityType
  typeLabel: string
  surface: string
  truth: string
  /** Normalized stage coordinates (x right, y down), origin top-left. */
  x: number
  y: number
}

export type LatticeRelation = {
  id: string
  from: string
  to: string
  label: string
}

export type LatticeSystemHint = {
  id: string
  name: string
  note: string
}

export const journeyWorldDemo = {
  source: 'data/worldpacks/journey-to-the-west.json',
  license: 'public-domain',
  entities: [
    {
      id: 'tang-seng',
      name: '唐僧',
      type: 'character',
      typeLabel: '人物',
      surface: '大唐御弟，奉旨西行取经，恪守戒律。',
      truth: '金蝉子转世；吃其肉可长生不老——这条设定驱动了多数妖魔动机。',
      x: 0.30,
      y: 0.37,
    },
    {
      id: 'sun-wukong',
      name: '孙悟空',
      type: 'character',
      typeLabel: '人物',
      surface: '七十二变、筋斗云、火眼金睛；嫉恶如仇。',
      truth: '战力受紧箍咒制约；「先动手再解释」正是师徒冲突的火药桶。',
      x: 0.65,
      y: 0.46,
    },
    {
      id: 'zhu-bajie',
      name: '猪八戒',
      type: 'character',
      typeLabel: '人物',
      surface: '前天蓬元帅，贪吃好色，关键时刻也能出力。',
      truth: '常在师父面前搬弄是非，是悟空被逐的主要推手。',
      x: 0.86,
      y: 0.25,
    },
    {
      id: 'guanyin',
      name: '观世音菩萨',
      type: 'character',
      typeLabel: '人物',
      surface: '点化取经团队，赐紧箍，危难时出手相助。',
      truth: '布局者之一：取经本身是一场被安排好的修行与招安。',
      x: 0.12,
      y: 0.16,
    },
    {
      id: 'baigu-furen',
      name: '白骨夫人',
      type: 'character',
      typeLabel: '人物',
      surface: '白虎岭尸魔，三变戏唐僧。',
      truth: '脊梁刻「白骨夫人」；她的死直接触发三打白骨精与师徒决裂。',
      x: 0.91,
      y: 0.72,
    },
    {
      id: 'huaguo-shan',
      name: '花果山',
      type: 'location',
      typeLabel: '地点',
      surface: '东胜神洲仙山，悟空故里。',
      truth: '被逐后的精神原点：每遇绝境，「回花果山」都是真实选项。',
      x: 0.38,
      y: 0.77,
    },
    {
      id: 'jingu-zhou',
      name: '紧箍咒',
      type: 'item',
      typeLabel: '物品',
      surface: '唐僧约束悟空的手段。',
      truth: '不对等的权力工具：师父肉眼凡胎，却掌握唯一能制服悟空的开关。',
      x: 0.77,
      y: 0.82,
    },
    {
      id: 'tianting',
      name: '天庭',
      type: 'faction',
      typeLabel: '势力',
      surface: '三界秩序的最高权威。',
      truth: '对悟空先是招安不成，后是借取经体系重新纳入秩序。',
      x: 0.56,
      y: 0.12,
    },
  ] as const satisfies readonly LatticeEntity[],
  relations: [
    { id: 'r1', from: 'tang-seng', to: 'sun-wukong', label: '师徒' },
    { id: 'r2', from: 'guanyin', to: 'sun-wukong', label: '约束' },
    { id: 'r3', from: 'tang-seng', to: 'zhu-bajie', label: '师徒' },
    { id: 'r4', from: 'sun-wukong', to: 'baigu-furen', label: '敌对' },
    { id: 'r5', from: 'baigu-furen', to: 'tang-seng', label: '觊觎' },
    { id: 'r6', from: 'zhu-bajie', to: 'sun-wukong', label: '挑拨' },
    { id: 'r7', from: 'tianting', to: 'sun-wukong', label: '招安-叛逆' },
    { id: 'r8', from: 'sun-wukong', to: 'huaguo-shan', label: '归处' },
    { id: 'r9', from: 'jingu-zhou', to: 'sun-wukong', label: '制约' },
  ] as const satisfies readonly LatticeRelation[],
  system: {
    id: 'team-hierarchy',
    name: '取经团队层级',
    note: '师父—徒弟—坐骑/护法：续写对话与行动权限时按此层级推导。',
  } as const satisfies LatticeSystemHint,
  stats: {
    entities: 8,
    relations: 9,
    systems: 1,
  },
} as const

export type JourneyWorldDemo = typeof journeyWorldDemo
