import { describe, expect, it } from 'vitest'
import {
  getNativeNovelFileContract,
  serializeChapterToNativeFormat,
  serializeChaptersToNativeFormat,
} from '@/lib/chaptersNativeFormat'
import type { Chapter, NovelContentFormat } from '@/types/api'

function chapter(partial: Partial<Chapter>): Chapter {
  return {
    id: 1,
    novel_id: 7,
    chapter_number: 1,
    title: '开端',
    source_chapter_label: '第一章 开端',
    source_chapter_number: 1,
    source_volume_title: null,
    content: '正文',
    created_at: '2026-01-01T00:00:00Z',
    updated_at: null,
    ...partial,
  }
}

describe('chaptersNativeFormat', () => {
  it('serializes Markdown volumes, internal chapter numbers, titles, and raw bodies', () => {
    const content = serializeChaptersToNativeFormat([
      chapter({ source_volume_title: '第一卷', content: '**正文**\n' }),
      chapter({ id: 2, chapter_number: 2, title: '继续', source_volume_title: '第一卷', content: '第二章正文' }),
      chapter({ id: 3, chapter_number: 3, title: '归来', source_volume_title: '第二卷', content: '> 引用\n' }),
    ], 'markdown')

    expect(content).toBe(
      '# 第一卷\n'
      + '## 第 1 章 · 开端\n'
      + '**正文**\n'
      + '## 第 2 章 · 继续\n'
      + '第二章正文\n'
      + '# 第二卷\n'
      + '## 第 3 章 · 归来\n'
      + '> 引用\n',
    )
    expect(getNativeNovelFileContract('markdown')).toEqual({
      extension: '.md',
      mimeType: 'text/markdown;charset=utf-8',
    })
  })

  it('exports one Markdown chapter with its volume and keeps plain text behavior', () => {
    const source = chapter({ source_volume_title: '第一卷' })
    expect(serializeChapterToNativeFormat(source, 'markdown')).toBe(
      '# 第一卷\n## 第 1 章 · 开端\n正文\n',
    )
    expect(serializeChapterToNativeFormat(source, 'plain_text')).toBe(
      '第 1 章 · 开端\n\n正文',
    )
  })

  it('fails fast on an unrepresentable named-volume to unscoped transition', () => {
    expect(() => serializeChaptersToNativeFormat([
      chapter({ source_volume_title: '第一卷' }),
      chapter({ id: 2, chapter_number: 2, source_volume_title: null }),
    ], 'markdown')).toThrow('cannot return to an unscoped chapter')
  })

  it('escapes plain volume and chapter metadata for a parser-safe Markdown round trip', () => {
    expect(serializeChapterToNativeFormat(chapter({
      source_volume_title: '第一 *卷* [草稿]',
      title: 'First *Star* [Draft] \\ path',
    }), 'markdown')).toBe(
      '# 第一 \\*卷\\* \\[草稿\\]\n'
      + '## 第 1 章 · First \\*Star\\* \\[Draft\\] \\\\ path\n'
      + '正文\n',
    )
  })

  it('rejects unknown novel formats instead of choosing a fallback export', () => {
    expect(() => getNativeNovelFileContract('rich_text' as NovelContentFormat)).toThrow(
      'Unsupported novel content format: rich_text',
    )
  })
})
