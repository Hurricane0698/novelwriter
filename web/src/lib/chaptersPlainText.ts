import type { Chapter } from '@/types/api'

export type ChapterLike = Pick<Chapter, 'chapter_number' | 'title' | 'content'>

export function stripLeadingChapterHeading(title: string): string {
  const t = title.trim()
  if (!t) return ''

  // Match both Arabic digits and Chinese numerals.
  // Examples:
  // - 第1章 开端
  // - 第一章 开端
  // - 第 12 回 归来
  const m = t.match(/^第\s*([0-9零一二三四五六七八九十百千万两〇]+)\s*[章回节]\s*/i)
  if (m) {
    let rest = t.slice(m[0].length).trim()
    rest = rest.replace(/^[·•\-—–:：、.．\s]+/, '').trim()
    return rest
  }

  // English-style headings: "Chapter 1 ..."
  const m2 = t.match(/^chapter\s+\d+\s*/i)
  if (m2) {
    let rest = t.slice(m2[0].length).trim()
    rest = rest.replace(/^[·•\-—–:：、.．\s]+/, '').trim()
    return rest
  }

  return t
}

/** Format chapter label: avoid "第 94 章 · 第93章虎魄" duplication. */
export function formatChapterLabel(
  chapterNumber: number,
  title: string | null | undefined
): string {
  const base = `第 ${chapterNumber} 章`
  const t = title ?? ''
  const rest = stripLeadingChapterHeading(t)
  if (!rest) return base
  return `${base} · ${rest}`
}

export function serializeChaptersToPlainText(chapters: ChapterLike[]): string {
  return chapters
    .map((c) => `${formatChapterLabel(c.chapter_number, c.title)}\n\n${c.content}`)
    .join('\n\n---\n\n')
}
