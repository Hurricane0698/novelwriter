import { useEffect, useLayoutEffect, useRef, useState } from 'react'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { api } from '@/services/api'
import { novelKeys } from './keys'
import type { Continuation } from '@/types/api'
import { useTextReviewTarget } from '@/hooks/novel-copilot/useTextReviewTarget'
import { useUiLocale } from '@/contexts/UiLocaleContext'
import { registerDesktopSave } from '@/lib/desktopExit'

export function useCandidateDraft({ novelId, candidateId, original, initial, enabled }: {
  novelId: number; candidateId: number | null; original: string; initial?: Continuation; enabled: boolean
}) {
  const { t } = useUiLocale()
  const qc = useQueryClient()
  const key = novelKeys.continuations(novelId, String(candidateId))
  const query = useQuery({ queryKey: key,
    queryFn: () => api.getContinuations(novelId, [candidateId!]),
    enabled: enabled && candidateId !== null, retry: false,
  })
  const saved = query.data?.[0] ?? initial
  const savedContent = saved?.edited_content ?? saved?.content ?? original
  const [drafts, setDrafts] = useState<Record<number, { content: string; hash: string }>>({})
  const draftsRef = useRef(drafts)
  useLayoutEffect(() => { draftsRef.current = drafts }, [drafts])
  const [viewState, setViewState] = useState<{ id: number | null; view: 'original' | 'current' | 'edit' }>({ id: null, view: 'current' })
  const view = viewState.id === candidateId ? viewState.view : 'current'
  const setView = (next: typeof view) => setViewState({ id: candidateId, view: next })
  const [saving, setSaving] = useState(false)
  const savingRef = useRef<Promise<boolean> | null>(null)
  const [error, setError] = useState('')
  useEffect(() => registerDesktopSave(async () => {
    await savingRef.current
    for (const [id, draft] of Object.entries(draftsRef.current)) {
      const updated = await api.updateContinuation(novelId, Number(id), draft.content, draft.hash)
      qc.setQueryData(novelKeys.continuations(novelId, id), [updated])
      setDrafts((current) => {
        const next = { ...current }
        if (next[Number(id)]?.content === draft.content) delete next[Number(id)]
        draftsRef.current = next
        return next
      })
    }
  }), [novelId, qc])
  const content = candidateId !== null ? (drafts[candidateId]?.content ?? savedContent) : original

  const accept = (row: Continuation) => {
    qc.setQueryData(key, [row])
    void qc.invalidateQueries({ queryKey: ['novels', novelId, 'continuations'], refetchType: 'none' })
  }
  const flush = async () => {
    if (savingRef.current) return savingRef.current
    if (candidateId === null) return false
    const draft = draftsRef.current[candidateId]
    if (!draft) return true
    setSaving(true)
    setError('')
    const request = api.updateContinuation(novelId, candidateId, draft.content, draft.hash)
      .then((row) => {
        accept(row)
        setDrafts((current) => {
          const remaining = { ...current }
          if (remaining[candidateId]?.content === draft.content) delete remaining[candidateId]
          else if (remaining[candidateId] && row.content_hash) remaining[candidateId] = { ...remaining[candidateId], hash: row.content_hash }
          draftsRef.current = remaining
          return remaining
        })
        return true
      }).catch((error: unknown) => { setError(t('review.failed')); throw error })
      .finally(() => { savingRef.current = null; setSaving(false) })
    savingRef.current = request
    return request
  }
  const ready = enabled && candidateId !== null && Boolean(saved?.content_hash)
  const review = useTextReviewTarget({
    target: ready ? { kind: 'continuation', id: candidateId!, chapter_number: saved?.chapter_number,
      label: `${t('review.candidate')} · ${candidateId}` } : null,
    content, flush,
    accept: (change) => {
      if (!saved || candidateId === null) return
      accept({ ...saved, edited_content: change.content, content_hash: change.content_hash })
      setDrafts((current) => { const next = { ...current }; delete next[candidateId]; draftsRef.current = next; return next })
      setView('current')
    },
    save: async (body, hash) => { accept(await api.updateContinuation(novelId, candidateId!, body, hash)) },
  })
  return {
    content, original: saved?.content ?? original, view, setView, ready, error,
    busy: saving || review.busy, saving, openReview: review.openReview, flush,
    edited: saved?.edited_content != null || (candidateId !== null && drafts[candidateId] !== undefined),
    unsaved: candidateId !== null && drafts[candidateId] !== undefined,
    change: (next: string) => {
      if (candidateId === null || !saved?.content_hash || savingRef.current || review.isLocked()) return
      const nextDrafts = { ...draftsRef.current, [candidateId]: { content: next,
        hash: draftsRef.current[candidateId]?.hash ?? saved.content_hash } }
      draftsRef.current = nextDrafts
      setDrafts(nextDrafts)
    },
  }
}
