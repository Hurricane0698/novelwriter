import { webcrypto } from 'node:crypto'
import { act, render, renderHook, waitFor } from '@testing-library/react'
import { afterEach, beforeEach, expect, it, vi } from 'vitest'
import { api } from '@/services/api'
import { novelKeys } from '@/hooks/novel/keys'
import { useCandidateDraft } from '@/hooks/novel/useCandidateDraft'
import { useNovelCopilot } from '@/components/novel-copilot/NovelCopilotContext'
import { CandidateDraftPersistence } from '@/components/CandidateDraftPersistence'
import { createTestQueryClient } from './support/queryClient'
import { createNovelWrapper } from './support/novel'
import { continuation, deferred } from './support/continuation'
import type { Continuation } from '@/types/api'

const exitSaves = new Set<() => Promise<void>>()
vi.mock('@/lib/desktopExit', () => ({ registerDesktopSave: (save: () => Promise<void>) => {
  exitSaves.add(save)
  return () => { exitSaves.delete(save) }
} }))
vi.mock('@/services/api', async (importOriginal) => ({
  ...await importOriginal<typeof import('@/services/api')>(),
  api: { getContinuations: vi.fn(), updateContinuation: vi.fn() },
}))

beforeEach(() => {
  vi.resetAllMocks()
  vi.stubGlobal('crypto', webcrypto)
  localStorage.clear()
  exitSaves.clear()
})
afterEach(() => vi.unstubAllGlobals())

function setup() {
  const client = createTestQueryClient()
  client.setDefaultOptions({ queries: { retry: false, staleTime: Infinity, gcTime: Infinity } })
  const rows = new Map([11, 12].map((id) => [id, continuation(id, `原稿${id}`)]))
  rows.forEach((row) => client.setQueryData(novelKeys.continuations(7, String(row.id)), [row]))
  vi.mocked(api.getContinuations).mockImplementation(async (_novelId, ids) => ids.map((id) => rows.get(id)!))
  vi.mocked(api.updateContinuation).mockImplementation(async (_novelId, id, content) => {
    const updated = { ...rows.get(id)!, edited_content: content, content_hash: continuation(id, content).content_hash }
    rows.set(id, updated)
    return updated
  })
  const wrapper = createNovelWrapper(client)
  const mount = (id = 11) => renderHook(({ id, novelId }) => ({
    draft: useCandidateDraft({ novelId, candidateId: id, original: `原稿${id}`, enabled: true }),
    copilot: useNovelCopilot(),
  }), { wrapper, initialProps: { id, novelId: 7 } })
  return { client, rows, wrapper, mount }
}

it('retains both unsaved candidates after leaving results and remounting', async () => {
  const { mount } = setup()
  const view = mount()
  act(() => { view.result.current.draft.change('修改稿11') })
  view.rerender({ id: 12, novelId: 7 })
  act(() => { view.result.current.draft.change('修改稿12') })
  view.unmount()

  const returned = mount()
  expect(returned.result.current.draft).toMatchObject({ content: '修改稿11', original: '原稿11', unsaved: true })
  returned.rerender({ id: 12, novelId: 7 })
  expect(returned.result.current.draft).toMatchObject({ content: '修改稿12', original: '原稿12', unsaved: true })
  expect(api.updateContinuation).not.toHaveBeenCalled()

  // A review/source-navigation preparation joins the same save queue for both drafts.
  await act(async () => {
    await returned.result.current.copilot.getTextTarget({ kind: 'continuation', id: 12 })!.prepare()
  })
  expect(api.updateContinuation).toHaveBeenNthCalledWith(1, 7, 11, '修改稿11', continuation(11, '原稿11').content_hash)
  expect(api.updateContinuation).toHaveBeenNthCalledWith(2, 7, 12, '修改稿12', continuation(12, '原稿12').content_hash)
  await waitFor(() => expect(returned.result.current.draft.unsaved).toBe(false))
})

it('keeps failed saves through navigation and retries with the original content hash', async () => {
  const { mount } = setup()
  const view = mount()
  act(() => { view.result.current.draft.change('待保存手稿') })
  vi.mocked(api.updateContinuation).mockRejectedValueOnce(new Error('offline'))
  await act(async () => { await expect(view.result.current.draft.flush()).rejects.toThrow('offline') })
  view.unmount()

  const returned = mount()
  expect(returned.result.current.draft).toMatchObject({ content: '待保存手稿', unsaved: true })
  expect(returned.result.current.draft.error).not.toBe('')
  await act(async () => { await returned.result.current.draft.flush() })
  await waitFor(() => expect(returned.result.current.draft.unsaved).toBe(false))
  expect(api.updateContinuation).toHaveBeenLastCalledWith(7, 11, '待保存手稿', continuation(11, '原稿11').content_hash)
  expect(returned.result.current.draft.original).toBe('原稿11')
})

it('saves closed editors on desktop exit and joins a save already in flight', async () => {
  const { mount, wrapper, rows } = setup()
  const app = render(<CandidateDraftPersistence />, { wrapper })
  const view = mount()
  act(() => { view.result.current.draft.change('退出前的修改') })
  const pending = deferred<Continuation>()
  vi.mocked(api.updateContinuation).mockReturnValueOnce(pending.promise)
  let manual!: Promise<boolean>
  act(() => { manual = view.result.current.draft.flush() })
  view.unmount()

  expect(exitSaves.size).toBe(1)
  let exiting!: Promise<void[]>
  act(() => { exiting = Promise.all([...exitSaves].map((save) => save())) })
  expect(api.updateContinuation).toHaveBeenCalledTimes(1)
  await act(async () => {
    pending.resolve({ ...rows.get(11)!, edited_content: '退出前的修改', content_hash: continuation(11, '退出前的修改').content_hash })
    await Promise.all([manual, exiting])
  })
  const returned = mount()
  expect(returned.result.current.draft).toMatchObject({ content: '退出前的修改', original: '原稿11', unsaved: false })
  app.unmount()
  expect(exitSaves.size).toBe(0)
})

it('does not resend a candidate that saved before another candidate failed', async () => {
  const { mount, rows } = setup()
  const view = mount()
  act(() => { view.result.current.draft.change('修改稿11') })
  view.rerender({ id: 12, novelId: 7 })
  act(() => { view.result.current.draft.change('修改稿12') })
  vi.mocked(api.updateContinuation)
    .mockResolvedValueOnce({ ...rows.get(11)!, edited_content: '修改稿11' })
    .mockRejectedValueOnce(new Error('conflict'))
  await act(async () => { await expect(view.result.current.draft.flush()).rejects.toThrow('conflict') })
  await act(async () => { await view.result.current.draft.flush() })
  expect(vi.mocked(api.updateContinuation).mock.calls.map((call) => call[1])).toEqual([11, 12, 12])
})

it('keeps drafts isolated by novel and discards late completions after logout', async () => {
  const { mount, client, rows } = setup()
  const view = mount()
  act(() => { view.result.current.draft.change('小说7手稿') })
  view.rerender({ id: 11, novelId: 8 })
  expect(view.result.current.draft.content).toBe('原稿11')
  view.rerender({ id: 11, novelId: 7 })
  expect(view.result.current.draft.content).toBe('小说7手稿')
  const pending = deferred<Continuation>()
  vi.mocked(api.updateContinuation).mockReturnValueOnce(pending.promise)
  let saving!: Promise<boolean>
  act(() => { saving = view.result.current.draft.flush() })
  view.unmount()
  client.clear()
  await act(async () => {
    pending.resolve({ ...rows.get(11)!, edited_content: '小说7手稿' })
    await saving
  })
  expect(client.getQueryCache().getAll()).toHaveLength(0)
})
