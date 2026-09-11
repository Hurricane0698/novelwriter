// SPDX-FileCopyrightText: 2026 Isaac.X.Ω.Yuan
// SPDX-License-Identifier: AGPL-3.0-only

/** Verbatim excerpt from data/demo/西游记_前27回.txt, chapter 27 (public domain). */
export const chapter27Excerpt = {
  spans: [
    { kind: 'entity', text: '唐僧', entityId: 'tang-seng' },
    { kind: 'text', text: '正要' },
    { kind: 'system', text: '念咒', systemId: 'jingu-zhou' },
    { kind: 'text', text: '，' },
    { kind: 'entity', text: '行者', entityId: 'sun-wukong' },
    { kind: 'text', text: '急到马前，叫道：“师父，莫念！莫念！你且来看看他的模样。”却是一堆粉骷髅在那里。唐僧大惊道：“悟空，这个人才死了，怎么就化作一堆骷髅？”行者道：“他是个潜灵作怪的僵尸，在此迷人败本；被我打杀，他就现了本相。他那脊梁上有一行字，叫做‘' },
    { kind: 'entity', text: '白骨夫人', entityId: 'baigu-furen' },
    { kind: 'text', text: '’。”' },
  ],
  injection: {
    entityIds: ['tang-seng', 'sun-wukong', 'baigu-furen'],
    relationIds: ['r1', 'r4'],
    systemIds: ['jingu-zhou'],
  },
} as const
