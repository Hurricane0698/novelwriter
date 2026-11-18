import { useState } from 'react'
import { skipToken, useQuery, useQueryClient } from '@tanstack/react-query'
import { api } from '@/services/api'
import { novelKeys } from './keys'
import type { Continuation } from '@/types/api'
import { useTextReviewTarget } from '@/hooks/novel-copilot/useTextReviewTarget'
import { useUiLocale } from '@/contexts/UiLocaleContext'
import {
  acceptCandidate, candidateDraftKeys, changeCandidateDraft, emptyCandidateDrafts,
  saveCandidateDrafts,
} from './candidateDrafts'

type DraftView = 'original' | 'current' | 'edit'

export function useCandidateDraft({ novelId, candidateId, original, initial, enabled }: {
  novelId: number; candidateId: number | null; original: string; initial?: Continuation; enabled: boolean
}) {
  const { t } = useUiLocale()
  const client = useQueryClient()
  const query = useQuery({
    queryKey: novelKeys.continuations(novelId, String(candidateId)),
    queryFn: () => api.getContinuations(novelId, [candidateId!]),
    enabled: enabled && candidateId !== null,
    retry: false,
  })
  // Drafts belong to the application session, not the mounted results page.
  const { data: state = emptyCandidateDrafts } = useQuery({
    queryKey: candidateDraftKeys.novel(novelId),
    queryFn: skipToken,
    initialData: emptyCandidateDrafts,
    enabled: false,
    gcTime: Infinity,
  })
  const saved = query.data?.[0] ?? initial
  const draft = candidateId === null ? undefined : state.drafts[candidateId]
  const content = draft?.content ?? saved?.edited_content ?? saved?.content ?? original
  const [viewState, setViewState] = useState<{ id: number | null; view: DraftView }>({ id: null, view: 'current' })
  const view = viewState.id === candidateId ? viewState.view : 'current'
  const setView = (next: DraftView) => setViewState({ id: candidateId, view: next })
  const flush = async () => {
    await saveCandidateDrafts(client, novelId)
    return candidateId !== null
  }
  const ready = enabled && candidateId !== null && Boolean(saved?.content_hash)
  const review = useTextReviewTarget({
    target: ready ? {
      kind: 'continuation', id: candidateId!, chapter_number: saved?.chapter_number,
      label: `${t('review.candidate')} · ${candidateId}`,
    } : null,
    content,
    flush,
    accept: (change) => {
      if (!saved) return
      acceptCandidate(client, { ...saved, edited_content: change.content, content_hash: change.content_hash })
      setView('current')
    },
    save: async (body, hash) => {
      acceptCandidate(client, await api.updateContinuation(novelId, candidateId!, body, hash))
    },
  })
  return {
    content, original: saved?.content ?? original, view, setView, ready,
    error: state.failed ? t('review.failed') : '',
    busy: state.saving || review.busy,
    saving: state.saving,
    openReview: review.openReview,
    flush,
    edited: saved?.edited_content != null || draft !== undefined,
    unsaved: draft !== undefined,
    change: (next: string) => {
      if (candidateId === null || !saved?.content_hash || review.isLocked()) return
      changeCandidateDraft(client, novelId, candidateId, next, saved.content_hash)
    },
  }
}
