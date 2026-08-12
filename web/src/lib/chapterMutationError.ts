import { ApiError } from '@/services/apiClient'

export const MARKDOWN_CHAPTER_BODY_INVALID = 'markdown_chapter_body_invalid' as const

export type ChapterMutationErrorCode = typeof MARKDOWN_CHAPTER_BODY_INVALID

export function isMarkdownChapterBodyInvalidError(
  error: unknown,
): error is ApiError & { code: ChapterMutationErrorCode } {
  return (
    error instanceof ApiError
    && error.status === 422
    && error.code === MARKDOWN_CHAPTER_BODY_INVALID
  )
}
