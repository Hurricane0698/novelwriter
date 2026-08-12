import { formatChapterLabel, serializeChaptersToPlainText } from '@/lib/chaptersPlainText'
import { isMarkdownContentFormat } from '@/lib/novelContentFormat'
import type { Chapter, NovelContentFormat } from '@/types/api'

export interface NativeNovelFileContract {
  extension: '.txt' | '.md'
  mimeType: 'text/plain;charset=utf-8' | 'text/markdown;charset=utf-8'
}

const MARKDOWN_ESCAPABLE_PUNCTUATION_RE = /[!"#$%&'()*+,\-./:;<=>?@[\\\]^_`{|}~]/g

function escapeMarkdownHeadingText(value: string): string {
  return value.replace(MARKDOWN_ESCAPABLE_PUNCTUATION_RE, (character) => `\\${character}`)
}

export function getNativeNovelFileContract(
  contentFormat: NovelContentFormat,
): NativeNovelFileContract {
  if (!isMarkdownContentFormat(contentFormat)) {
    return {
      extension: '.txt',
      mimeType: 'text/plain;charset=utf-8',
    }
  }
  return {
    extension: '.md',
    mimeType: 'text/markdown;charset=utf-8',
  }
}

function markdownChapterBlock(chapter: Chapter, includeVolume: boolean): string {
  const volumeHeading = includeVolume && chapter.source_volume_title
    ? `# ${escapeMarkdownHeadingText(chapter.source_volume_title)}\n`
    : ''
  const structuralHeadings = `${volumeHeading}## ${escapeMarkdownHeadingText(formatChapterLabel(chapter))}\n`
  const body = chapter.content
  return `${structuralHeadings}${body}${body.endsWith('\n') ? '' : '\n'}`
}

export function serializeChapterToNativeFormat(
  chapter: Chapter,
  contentFormat: NovelContentFormat,
): string {
  if (!isMarkdownContentFormat(contentFormat)) {
    return serializeChaptersToPlainText([chapter])
  }
  return markdownChapterBlock(chapter, true)
}

export function serializeChaptersToNativeFormat(
  chapters: Chapter[],
  contentFormat: NovelContentFormat,
): string {
  if (!isMarkdownContentFormat(contentFormat)) return serializeChaptersToPlainText(chapters)

  let activeVolume: string | null = null
  return chapters.map((chapter) => {
    if (activeVolume !== null && chapter.source_volume_title === null) {
      throw new Error('Markdown volume metadata cannot return to an unscoped chapter')
    }
    const includeVolume = chapter.source_volume_title !== activeVolume
    if (includeVolume) activeVolume = chapter.source_volume_title
    return markdownChapterBlock(chapter, includeVolume)
  }).join('')
}
