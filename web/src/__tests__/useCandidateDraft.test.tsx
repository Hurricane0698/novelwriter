import type { ReactNode } from 'react'
import { act, renderHook } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { expect, it, vi } from 'vitest'
import { api } from '@/services/api'
import { novelKeys } from '@/hooks/novel/keys'
import { useCandidateDraft } from '@/hooks/novel/useCandidateDraft'

let saveOnExit: (() => Promise<void>) | undefined
vi.mock('@/lib/desktopExit', () => ({ registerDesktopSave: (save: () => Promise<void>) => {
  saveOnExit = save
  return () => { saveOnExit = undefined }
} }))
vi.mock('@/contexts/UiLocaleContext', () => ({ useUiLocale: () => ({ t: (key: string) => key }) }))
vi.mock('@/hooks/novel-copilot/useTextReviewTarget', () => ({ useTextReviewTarget: () => ({
  busy: false, isLocked: () => false, openReview: vi.fn(),
}) }))
vi.mock('@/services/api', () => ({ api: { getContinuations: vi.fn(), updateContinuation: vi.fn() } }))

it('saves drafts from both candidates before desktop exit, preserving their original text', async () => {
  const qc = new QueryClient({ defaultOptions: { queries: { staleTime: Infinity, retry: false } } })
  for (const id of [11, 12]) qc.setQueryData(novelKeys.continuations(1, String(id)), [{
    id, novel_id: 1, chapter_number: 3, content: `原稿${id}`, edited_content: null, content_hash: `hash${id}`,
  }])
  vi.mocked(api.updateContinuation).mockImplementation(async (_novelId, id, content) => ({
    id, novel_id: 1, chapter_number: 3, content: `原稿${id}`, edited_content: content, content_hash: `saved${id}`,
  }))
  const wrapper = ({ children }: { children: ReactNode }) => <QueryClientProvider client={qc}>{children}</QueryClientProvider>
  const view = renderHook(({ id }) => useCandidateDraft({ novelId: 1, candidateId: id,
    original: `原稿${id}`, enabled: true,
  }), { wrapper, initialProps: { id: 11 } })
  act(() => { view.result.current.change('修改稿11') })
  view.rerender({ id: 12 })
  act(() => { view.result.current.change('修改稿12') })
  await act(async () => { await saveOnExit!() })
  expect(api.updateContinuation).toHaveBeenNthCalledWith(1, 1, 11, '修改稿11', 'hash11')
  expect(api.updateContinuation).toHaveBeenNthCalledWith(2, 1, 12, '修改稿12', 'hash12')
  expect(view.result.current).toMatchObject({ content: '修改稿12', original: '原稿12', unsaved: false })
  view.rerender({ id: 11 })
  expect(view.result.current).toMatchObject({ content: '修改稿11', original: '原稿11', unsaved: false })
  view.unmount()
  expect(saveOnExit).toBeUndefined()
})
