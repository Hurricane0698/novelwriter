import type { Query, QueryClient } from '@tanstack/react-query'
import { api } from '@/services/api'
import type { Continuation } from '@/types/api'
import { novelKeys } from './keys'

interface CandidateDraft {
  content: string
  hash: string
}

interface CandidateDraftState {
  drafts: Record<number, CandidateDraft>
  saving: boolean
  failed: boolean
}

export const candidateDraftKeys = {
  all: ['candidate-drafts'] as const,
  novel: (novelId: number) => ['candidate-drafts', novelId] as const,
}
export const emptyCandidateDrafts: CandidateDraftState = { drafts: {}, saving: false, failed: false }
const saves = new WeakMap<Query, Promise<void>>()

function getCandidateDrafts(client: QueryClient, novelId: number) {
  return client.getQueryData<CandidateDraftState>(candidateDraftKeys.novel(novelId)) ?? emptyCandidateDrafts
}

function updateState(client: QueryClient, novelId: number, update: (state: CandidateDraftState) => CandidateDraftState) {
  client.setQueryData<CandidateDraftState>(candidateDraftKeys.novel(novelId), (state) => update(state ?? emptyCandidateDrafts))
}

export function changeCandidateDraft(client: QueryClient, novelId: number, id: number, content: string, hash: string) {
  updateState(client, novelId, (state) => state.saving ? state : {
    ...state,
    failed: false,
    drafts: { ...state.drafts, [id]: { content, hash: state.drafts[id]?.hash ?? hash } },
  })
}

export function acceptCandidate(client: QueryClient, row: Continuation) {
  client.setQueryData(novelKeys.continuations(row.novel_id, String(row.id)), [row])
  void client.invalidateQueries({ queryKey: ['novels', row.novel_id, 'continuations'], refetchType: 'none' })
  updateState(client, row.novel_id, (state) => {
    const drafts = { ...state.drafts }
    delete drafts[row.id]
    return { ...state, drafts }
  })
}

/** One save queue per novel, shared by review, adoption, manual save and exit. */
export function saveCandidateDrafts(client: QueryClient, novelId: number): Promise<void> {
  const query = client.getQueryCache().find({ queryKey: candidateDraftKeys.novel(novelId), exact: true })
  if (!query) return Promise.resolve()
  const existing = saves.get(query)
  if (existing) return existing
  const drafts = Object.entries(getCandidateDrafts(client, novelId).drafts)
  if (!drafts.length) return Promise.resolve()

  // Ignore completions after logout clears the owning query cache.
  const isCurrent = () => client.getQueryCache().find({ queryKey: candidateDraftKeys.novel(novelId), exact: true }) === query
  updateState(client, novelId, (state) => ({ ...state, saving: true, failed: false }))
  const request = (async () => {
    try {
      for (const [id, draft] of drafts) {
        if (!isCurrent()) return
        const row = await api.updateContinuation(novelId, Number(id), draft.content, draft.hash)
        if (!isCurrent()) return
        acceptCandidate(client, row)
      }
    } catch (error) {
      if (isCurrent()) updateState(client, novelId, (state) => ({ ...state, failed: true }))
      throw error
    } finally {
      if (isCurrent()) updateState(client, novelId, (state) => ({ ...state, saving: false }))
      saves.delete(query)
    }
  })()
  saves.set(query, request)
  return request
}

export async function saveAllCandidateDrafts(client: QueryClient) {
  const results = await Promise.allSettled(client.getQueryCache()
    .findAll({ queryKey: candidateDraftKeys.all })
    .map((query) => saveCandidateDrafts(client, Number(query.queryKey[1]))))
  const failure = results.find((result) => result.status === 'rejected')
  if (failure) throw failure.reason
}
