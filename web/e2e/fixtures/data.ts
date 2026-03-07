import { Novel, Chapter } from './types'

export const NOVELS: Novel[] = [
  { id: 1, title: '三体', author: '刘慈欣', file_path: '/novels/1', total_chapters: 5, created_at: '2026-01-01T00:00:00Z', updated_at: '2026-01-02T00:00:00Z' },
  { id: 2, title: '流浪地球', author: '刘慈欣', file_path: '/novels/2', total_chapters: 3, created_at: '2026-01-01T00:00:00Z', updated_at: '2026-01-03T00:00:00Z' },
]

export const CHAPTERS: Chapter[] = [
  { id: 1, novel_id: 1, chapter_number: 1, title: '第一章 科学边界', content: '汪淼觉得眼前的世界变得越来越奇怪了。', created_at: '2026-01-01T00:00:00Z' },
  { id: 2, novel_id: 1, chapter_number: 2, title: '第二章 射手和农场主', content: '科学的尽头是哲学，哲学的尽头是宗教。', created_at: '2026-01-01T00:00:00Z' },
]
