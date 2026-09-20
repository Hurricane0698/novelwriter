import { useLayoutEffect, useRef, useState } from 'react'
import { useNovelCopilot } from '@/components/novel-copilot/NovelCopilotContext'
import type { CopilotTextTarget, TextChange } from '@/types/copilot'

export async function hashText(content: string) {
  const digest = await crypto.subtle.digest('SHA-256', new TextEncoder().encode(content))
  return Array.from(new Uint8Array(digest), (byte) => byte.toString(16).padStart(2, '0')).join('')
}

/** Share the mounted editor's save queue, without retaining callbacks after navigation. */
export function useTextReviewTarget(options: {
  target: CopilotTextTarget | null
  content: string
  flush: () => Promise<boolean>
  accept: (change: TextChange) => void
  save: (content: string, expectedHash: string) => Promise<void>
  selection?: () => { start?: number; end?: number }
}) {
  const { registerTextTarget, openDrawer } = useNovelCopilot()
  const latest = useRef(options)
  const locked = useRef(false)
  const [busy, setBusy] = useState(false)
  const identity = options.target ? `${options.target.kind}:${options.target.id}` : null
  const activeIdentity = useRef(identity)
  useLayoutEffect(() => { latest.current = options; activeIdentity.current = identity })
  useLayoutEffect(() => () => { activeIdentity.current = null }, [])

  useLayoutEffect(() => {
    if (!options.target || !identity || !registerTextTarget) return
    const guard = () => {
      if (activeIdentity.current !== identity) throw new Error('Text editor changed')
    }
    const run = async <T,>(operation: (captured: typeof options) => Promise<T>) => {
      guard()
      if (locked.current) throw new Error('Text editor is saving')
      locked.current = true
      setBusy(true)
      const captured = latest.current
      try {
        if (!await captured.flush()) throw new Error('Text changed during save')
        guard()
        return await operation(captured)
      } finally { locked.current = false; setBusy(false) }
    }
    return registerTextTarget(options.target, {
      withSavedText: (operation) => run(() => operation()),
      prepare: () => run(async (captured) => ({
        ...captured.target!, content_hash: await hashText(captured.content), ...captured.selection?.(),
      })),
      write: (operation) => run(async (captured) => {
        const result = await operation()
        if (activeIdentity.current === identity) captured.accept(result)
        return result
      }),
      restore: (content, expectedHash) => run(async (captured) => {
        if (await hashText(captured.content) !== expectedHash) throw new Error('Text changed after apply')
        await captured.save(content, expectedHash)
        const result = { content, content_hash: await hashText(content), before_content: captured.content }
        if (activeIdentity.current === identity) captured.accept(result)
        return result
      }),
    })
  }, [identity, registerTextTarget, options.target?.kind, options.target?.id]) // eslint-disable-line react-hooks/exhaustive-deps

  return {
    busy,
    isLocked: () => locked.current,
    openReview: () => {
      if (options.target) openDrawer({ mode: 'research', scope: 'whole_book',
        context: { surface: 'studio', stage: options.target.kind === 'chapter' ? 'chapter' : 'results', text_target: options.target },
      }, { displayTitle: options.target.label })
    },
  }
}
