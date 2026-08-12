import type { NovelContentFormat } from '@/types/api'

function unsupportedContentFormat(contentFormat: never): never {
  throw new Error(`Unsupported novel content format: ${String(contentFormat)}`)
}

export function isMarkdownContentFormat(contentFormat: NovelContentFormat): boolean {
  switch (contentFormat) {
    case 'plain_text':
      return false
    case 'markdown':
      return true
    default:
      return unsupportedContentFormat(contentFormat)
  }
}
