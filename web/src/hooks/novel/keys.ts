export const novelKeys = {
  all: ['novels'] as const,
  detail: (id: number) => ['novels', id] as const,
  chapters: (id: number) => ['novels', id, 'chapters'] as const,
  chaptersMeta: (id: number) => ['novels', id, 'chapters', 'meta'] as const,
  chapter: (id: number, num: number) => ['novels', id, 'chapters', num] as const,
}
