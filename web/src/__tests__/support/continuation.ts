import { createHash } from 'node:crypto'
import type { Chapter, Continuation } from '@/types/api'

export function continuation(id: number, content: string, novelId = 7): Continuation {
  return {
    id, novel_id: novelId, chapter_number: 4, content,
    content_hash: createHash('sha256').update(content).digest('hex'),
    edited_content: null, rating: null, created_at: '2026-03-03T00:00:00Z',
  }
}

export function adoptedChapter(content: string): Chapter {
  return {
    id: 301, novel_id: 7, chapter_number: 4, title: '', content,
    source_chapter_label: null, source_chapter_number: null, source_volume_title: null,
    created_at: '2026-03-03T00:00:00Z', updated_at: null,
  }
}

export function deferred<T>() {
  let resolve!: (value: T | PromiseLike<T>) => void
  let reject!: (reason?: unknown) => void
  const promise = new Promise<T>((resolvePromise, rejectPromise) => {
    resolve = resolvePromise
    reject = rejectPromise
  })
  return { promise, resolve, reject }
}
