import { describe, expect, it } from 'vitest'
import {
  isMarkdownChapterBodyInvalidError,
  MARKDOWN_CHAPTER_BODY_INVALID,
} from '@/lib/chapterMutationError'
import { ApiError } from '@/services/apiClient'

describe('chapterMutationError', () => {
  it('recognizes the structured Markdown body rejection from the API', () => {
    const error = new ApiError(422, 'HTTP 422', {
      code: MARKDOWN_CHAPTER_BODY_INVALID,
      detail: {
        code: MARKDOWN_CHAPTER_BODY_INVALID,
        message: 'server diagnostic is not a frontend control-flow input',
      },
    })

    expect(isMarkdownChapterBodyInvalidError(error)).toBe(true)
  })

  it.each([
    new ApiError(500, 'HTTP 500', { code: MARKDOWN_CHAPTER_BODY_INVALID }),
    new ApiError(422, 'HTTP 422', { code: 'another_error' }),
    { status: 422, code: MARKDOWN_CHAPTER_BODY_INVALID },
  ])('rejects errors outside the exact ApiError status/code contract', (error) => {
    expect(isMarkdownChapterBodyInvalidError(error)).toBe(false)
  })
})
