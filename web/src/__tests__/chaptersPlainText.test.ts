import { describe, it, expect } from 'vitest'
import { formatChapterLabel, stripLeadingChapterHeading } from '@/lib/chaptersPlainText'

describe('chaptersPlainText', () => {
  it('stripLeadingChapterHeading strips CN/EN chapter headings', () => {
    expect(stripLeadingChapterHeading('第一章 开端')).toBe('开端')
    expect(stripLeadingChapterHeading('第1章 开端')).toBe('开端')
    expect(stripLeadingChapterHeading('第 12 回：归来')).toBe('归来')
    expect(stripLeadingChapterHeading('Chapter 1: Beginning')).toBe('Beginning')
    expect(stripLeadingChapterHeading('开端')).toBe('开端')
  })

  it('formatChapterLabel avoids duplicated headings like "第1章 第一章"', () => {
    expect(formatChapterLabel(1, '第一章 开端')).toBe('第 1 章 · 开端')
    expect(formatChapterLabel(1, '第1章 开端')).toBe('第 1 章 · 开端')
    expect(formatChapterLabel(1, '第一章')).toBe('第 1 章')
    expect(formatChapterLabel(1, null)).toBe('第 1 章')
  })
})

