import { describe, it, expect } from 'vitest'
import {
  formatChapterBadgeLabel,
  formatChapterLabel,
  getChapterDisplayTitle,
  matchesChapterSearch,
  serializeChaptersToPlainText,
  stripLeadingChapterHeading,
} from '@/lib/chaptersPlainText'

describe('chaptersPlainText', () => {
  it('stripLeadingChapterHeading strips only numbered chapter headings', () => {
    expect(stripLeadingChapterHeading('第一章 开端')).toBe('开端')
    expect(stripLeadingChapterHeading('第1章 开端')).toBe('开端')
    expect(stripLeadingChapterHeading('第 12 回：归来')).toBe('归来')
    expect(stripLeadingChapterHeading('Chapter 1: Beginning')).toBe('Beginning')
    expect(stripLeadingChapterHeading('序章')).toBe('序章')
    expect(stripLeadingChapterHeading('Prologue')).toBe('Prologue')
    expect(stripLeadingChapterHeading('开端')).toBe('开端')
  })

  it('always formats chapter labels from internal chapter numbering', () => {
    expect(formatChapterLabel({
      chapter_number: 1,
      title: '开端',
      source_chapter_label: '第一章 开端',
      source_chapter_number: 1,
    })).toBe('第 1 章 · 开端')
    expect(formatChapterLabel({
      chapter_number: 1,
      title: '新的标题',
      source_chapter_label: '第一章 开端',
      source_chapter_number: 1,
    })).toBe('第 1 章 · 新的标题')
    expect(formatChapterLabel({
      chapter_number: 1,
      title: '补记',
      source_chapter_label: '序章',
      source_chapter_number: null,
    })).toBe('第 1 章 · 补记')
    expect(formatChapterLabel({
      chapter_number: 1,
      title: null,
      source_chapter_label: null,
      source_chapter_number: null,
    })).toBe('第 1 章')
  })

  it('returns badge labels from internal chapter numbering', () => {
    expect(formatChapterBadgeLabel({
      chapter_number: 3,
      title: '归来',
      source_chapter_label: '第844章 归来',
      source_chapter_number: 844,
    })).toBe('第 3 章')
    expect(formatChapterBadgeLabel({
      chapter_number: 1,
      title: '',
      source_chapter_label: '序章',
      source_chapter_number: null,
    })).toBe('第 1 章')
    expect(formatChapterBadgeLabel({
      chapter_number: 7,
      title: '开端',
      source_chapter_label: null,
      source_chapter_number: null,
    })).toBe('第 7 章')
  })

  it('matches chapter search against internal numbers and titles only', () => {
    const importedChapter = {
      chapter_number: 3,
      title: '归来',
      source_chapter_label: '第844章 归来',
      source_chapter_number: 844,
    }
    expect(matchesChapterSearch(importedChapter, '844')).toBe(false)
    expect(matchesChapterSearch(importedChapter, '归来')).toBe(true)
    expect(matchesChapterSearch(importedChapter, '3')).toBe(true)
    expect(matchesChapterSearch(importedChapter, '无奈')).toBe(false)
  })

  it('keeps numeric matching exact for internal chapter identifiers while still matching visible title numbers', () => {
    expect(matchesChapterSearch({
      chapter_number: 17,
      title: '可真够懒的',
      source_chapter_label: null,
      source_chapter_number: null,
    }, '17')).toBe(true)
    expect(matchesChapterSearch({
      chapter_number: 420,
      title: '放一块',
      source_chapter_label: '第417章 放一块',
      source_chapter_number: 417,
    }, '417')).toBe(false)
    expect(matchesChapterSearch({
      chapter_number: 420,
      title: '无关章节',
      source_chapter_label: '第420章 无关章节',
      source_chapter_number: 420,
    }, '420')).toBe(true)
    expect(matchesChapterSearch({
      chapter_number: 17,
      title: '17号实验体',
      source_chapter_label: null,
      source_chapter_number: null,
    }, '17')).toBe(true)
    expect(matchesChapterSearch({
      chapter_number: 480,
      title: '无关章节',
      source_chapter_label: '第480章 无关章节',
      source_chapter_number: 480,
    }, '5')).toBe(false)
    expect(matchesChapterSearch({
      chapter_number: 480,
      title: '无关章节',
      source_chapter_label: '第480章 无关章节',
      source_chapter_number: 480,
    }, '50')).toBe(false)
  })

  it('normalizes editable titles even when old data still carries raw headings', () => {
    expect(getChapterDisplayTitle('第一章 开端')).toBe('开端')
    expect(getChapterDisplayTitle('序章')).toBe('序章')
    expect(getChapterDisplayTitle('Prologue')).toBe('Prologue')
    expect(getChapterDisplayTitle('开端')).toBe('开端')
  })

  it('keeps standalone special titles visible, searchable, and exportable', () => {
    const chapter = {
      chapter_number: 1,
      title: '序章',
      source_chapter_label: null,
      source_chapter_number: null,
      content: '故事开始。',
    }

    expect(formatChapterLabel(chapter)).toBe('第 1 章 · 序章')
    expect(matchesChapterSearch(chapter, '序章')).toBe(true)
    expect(serializeChaptersToPlainText([chapter])).toContain('第 1 章 · 序章\n\n故事开始。')
  })
})
