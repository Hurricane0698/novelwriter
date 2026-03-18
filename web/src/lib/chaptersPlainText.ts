import type { Chapter } from '@/types/api'

export type ChapterIdentityLike = Pick<
  Chapter,
  'chapter_number' | 'title' | 'source_chapter_label' | 'source_chapter_number'
>
export type ChapterLike = ChapterIdentityLike & Pick<Chapter, 'content'>

const SEARCH_IGNORED_CHARS = /[\s·•\-—–:：、.．]+/g
const HEADING_REST_SEPARATOR_RE = /^[\s·•\-—–:：、.．]+/
const FULLWIDTH_DIGIT_RE = /[０-９]/g
const NUMERIC_TOKEN_RE = /\d+/g
const NUMBERED_CJK_HEADING_RE = /^(\s*第\s*[0-9０-９零〇一二三四五六七八九十百千万兩两壱弐参肆伍陆陸柒捌玖拾佰仟萬貳叁]+\s*[章回节卷篇幕話话節編编巻卷])(.*)$/i
const KOREAN_NUMBERED_HEADING_RE = /^(\s*제\s*[0-9０-９]+\s*(?:장|화|편|막))(.*)$/i
const EN_NUMBERED_HEADING_RE = /^(\s*chapter\s+(?:\d+|[ivxlcdm]+))(.*)$/i

type ParsedHeading = {
  prefix: string
  title: string
}

function normalizeFullwidthDigits(text: string): string {
  return text.replace(FULLWIDTH_DIGIT_RE, (digit) => String.fromCharCode(digit.charCodeAt(0) - 0xFEE0))
}

function normalizeChapterSearchText(text: string): string {
  return normalizeFullwidthDigits(text).toLowerCase().replace(SEARCH_IGNORED_CHARS, '')
}

function normalizeNumericToken(token: string): string {
  const normalized = normalizeFullwidthDigits(token).replace(/^0+(?=\d)/, '')
  return normalized || '0'
}

function parseNumericQuery(query: string): string | null {
  const normalized = normalizeFullwidthDigits(query.trim())
  if (!/^\d+$/.test(normalized)) return null
  return normalizeNumericToken(normalized)
}

function extractNumericTokens(text: string): string[] {
  const matches = normalizeFullwidthDigits(text).match(NUMERIC_TOKEN_RE)
  if (!matches) return []
  return matches.map(normalizeNumericToken)
}

function cleanHeadingRest(rest: string): string {
  return rest.trim().replace(HEADING_REST_SEPARATOR_RE, '').trim()
}

function parseChapterHeading(label: string): ParsedHeading | null {
  const trimmed = label.trim()
  if (!trimmed) return null

  for (const pattern of [
    NUMBERED_CJK_HEADING_RE,
    KOREAN_NUMBERED_HEADING_RE,
    EN_NUMBERED_HEADING_RE,
  ]) {
    const match = trimmed.match(pattern)
    if (!match) continue
    return {
      prefix: match[1].trim(),
      title: cleanHeadingRest(match[2] ?? ''),
    }
  }

  return null
}

export function stripLeadingChapterHeading(title: string): string {
  const parsed = parseChapterHeading(title)
  if (!parsed) return title.trim()
  return parsed.title
}

export function getChapterDisplayTitle(title: string | null | undefined): string {
  return stripLeadingChapterHeading(title ?? '')
}

function formatInternalChapterLabel(chapterNumber: number, title: string | null | undefined): string {
  const base = `第 ${chapterNumber} 章`
  const rest = getChapterDisplayTitle(title)
  if (!rest) return base
  return `${base} · ${rest}`
}

export function formatChapterLabel(chapter: ChapterIdentityLike): string {
  return formatInternalChapterLabel(chapter.chapter_number, chapter.title)
}

export function formatChapterBadgeLabel(chapter: ChapterIdentityLike): string {
  return formatInternalChapterLabel(chapter.chapter_number, null)
}

export function matchesChapterSearch(
  chapter: ChapterIdentityLike,
  query: string,
): boolean {
  const rawQuery = query.trim()
  if (!rawQuery) return true

  const numericQuery = parseNumericQuery(rawQuery)
  if (numericQuery !== null) {
    const numericCandidates = new Set<string>()

    numericCandidates.add(normalizeNumericToken(String(chapter.chapter_number)))

    for (const text of [formatChapterLabel(chapter), getChapterDisplayTitle(chapter.title)]) {
      for (const token of extractNumericTokens(text)) {
        numericCandidates.add(token)
      }
    }

    return numericCandidates.has(numericQuery)
  }

  const normalizedQuery = normalizeChapterSearchText(rawQuery)
  const candidates = [
    normalizeChapterSearchText(formatChapterLabel(chapter)),
    normalizeChapterSearchText(getChapterDisplayTitle(chapter.title)),
  ]

  return candidates.some((candidate) => candidate.includes(normalizedQuery))
}

export function serializeChaptersToPlainText(chapters: ChapterLike[]): string {
  return chapters
    .map((chapter) => `${formatChapterLabel(chapter)}\n\n${chapter.content}`)
    .join('\n\n---\n\n')
}
