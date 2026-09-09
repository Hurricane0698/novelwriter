import { act, render, renderHook, waitFor } from '@testing-library/react'
import { useQuery } from '@tanstack/react-query'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { BootstrapPanel } from '@/components/world-model/shared/BootstrapPanel'
import { useBootstrapStatus, useTriggerBootstrap } from '@/hooks/world/useBootstrap'
import { worldKeys } from '@/hooks/world/keys'
import { worldApi } from '@/services/api'
import { createQueryClientWrapper, createTestQueryClient } from '@/__tests__/support/queryClient'
import type { BootstrapJobResponse } from '@/types/api'

vi.mock('@/services/api', () => ({
  worldApi: { getBootstrapStatus: vi.fn(), triggerBootstrap: vi.fn() },
  api: { getNovel: vi.fn().mockResolvedValue({ window_index: null }) },
  ApiError: class extends Error {},
}))
const t = (key: string) => key
vi.mock('@/contexts/UiLocaleContext', () => ({ useUiLocale: () => ({ locale: 'zh', t }) }))
vi.mock('@/components/world-model/shared/useToast', () => ({ useToast: () => ({ toast: vi.fn() }) }))

const job: BootstrapJobResponse = {
  job_id: 1, novel_id: 1, mode: 'initial', initialized: true, status: 'completed',
  progress: { step: 5, detail: 'Done' },
  result: { entities_found: 10, relationships_found: 5, index_refresh_only: false },
  error: null, created_at: '2026-01-01T00:00:00Z', updated_at: '2026-01-01T00:00:01Z',
}

function createReadyClient() {
  const client = createTestQueryClient()
  client.setDefaultOptions({ queries: { retry: false, gcTime: Infinity, staleTime: Infinity } })
  return client
}

describe('shared bootstrap terminal refresh', () => {
  beforeEach(() => vi.clearAllMocks())

  it('refreshes each world family once with a real page observer and BootstrapPanel', async () => {
    const client = createReadyClient()
    client.setQueryData(worldKeys.bootstrapStatus(1), { ...job, status: 'extracting' })
    const invalidations = vi.spyOn(client, 'invalidateQueries')
    let resolveEntities!: (value: { id: number }[]) => void
    const entities = vi.fn(() => new Promise<{ id: number }[]>(resolve => { resolveEntities = resolve }))
    const lifecycle = vi.fn()
    function Page() {
      useQuery({ queryKey: worldKeys.entities(1), queryFn: entities, initialData: [{ id: 1 }] })
      useBootstrapStatus(1)
      return <BootstrapPanel novelId={1} onLifecycleChange={lifecycle} />
    }
    const view = render(<Page />, { wrapper: createQueryClientWrapper(client) })
    expect(lifecycle).toHaveBeenCalledWith(expect.objectContaining({ phase: 'running' }))

    act(() => { client.setQueryData(worldKeys.bootstrapStatus(1), job) })
    await waitFor(() => expect(lifecycle).toHaveBeenCalledWith(expect.objectContaining({ phase: 'completed' })))
    expect(invalidations.mock.calls.map(([filters]) => filters?.queryKey)).toEqual([
      worldKeys.entities(1), worldKeys.relationships(1), worldKeys.systems(1),
    ])
    expect(entities).toHaveBeenCalledTimes(1)
    await act(async () => { resolveEntities([{ id: 2 }]) })
    expect(client.getQueryData(worldKeys.entities(1))).toEqual([{ id: 2 }])
    view.unmount()
  })

  it('shares first-terminal refresh across StrictMode observers, remounts and novel switches', async () => {
    const client = createReadyClient()
    client.setQueryData(worldKeys.bootstrapStatus(1), job)
    client.setQueryData(worldKeys.bootstrapStatus(2), { ...job, novel_id: 2 })
    const invalidations = vi.spyOn(client, 'invalidateQueries')
    const options = { wrapper: createQueryClientWrapper(client), reactStrictMode: true }
    const useObservers = ({ novelId }: { novelId: number }) => {
      useBootstrapStatus(novelId)
      useBootstrapStatus(novelId)
    }
    const first = renderHook(useObservers, { ...options, initialProps: { novelId: 1 } })
    expect(invalidations).toHaveBeenCalledTimes(3)
    first.rerender({ novelId: 2 })
    expect(invalidations).toHaveBeenCalledTimes(6)
    expect(invalidations).toHaveBeenCalledWith({ queryKey: worldKeys.entities(2) })
    first.rerender({ novelId: 1 })
    expect(invalidations).toHaveBeenCalledTimes(6)
    first.unmount()

    const remount = renderHook(useObservers, { ...options, initialProps: { novelId: 1 } })
    expect(invalidations).toHaveBeenCalledTimes(6)
    remount.unmount()
    client.setQueryData(worldKeys.bootstrapStatus(1), { ...job, updated_at: '2026-01-01T00:00:02Z' })
    const revised = renderHook(useObservers, { ...options, initialProps: { novelId: 1 } })
    expect(invalidations).toHaveBeenCalledTimes(9)
    revised.unmount()
  })

  it('refreshes failed and later terminal revisions after retry, without repeating identical data', async () => {
    const client = createReadyClient()
    client.setQueryData(worldKeys.bootstrapStatus(1), { ...job, status: 'failed', error: 'failure' })
    const invalidations = vi.spyOn(client, 'invalidateQueries')
    const view = renderHook(() => useBootstrapStatus(1), { wrapper: createQueryClientWrapper(client) })
    expect(invalidations).toHaveBeenCalledTimes(3)
    const update = async (data: BootstrapJobResponse | null, expected: number) => {
      act(() => { client.setQueryData(worldKeys.bootstrapStatus(1), data) })
      await waitFor(() => expect(view.result.current.data).toEqual(data))
      expect(invalidations).toHaveBeenCalledTimes(expected)
    }
    await update({ ...job, status: 'extracting' }, 3)
    await update({ ...job, job_id: 2 }, 6)
    await update({ ...job, job_id: 2 }, 6)
    await update({ ...job, job_id: 2, updated_at: '2026-01-01T00:00:03Z' }, 9)
    await update(null, 9)
    await update(job, 12)
    view.unmount()
  })

  it('recovers from a status request failure and gives recreated queries their own first refresh', async () => {
    const client = createReadyClient()
    const invalidations = vi.spyOn(client, 'invalidateQueries')
    vi.mocked(worldApi.getBootstrapStatus).mockRejectedValueOnce(new Error('offline')).mockResolvedValue(job)
    const options = { wrapper: createQueryClientWrapper(client) }
    const first = renderHook(() => useBootstrapStatus(1), options)
    await waitFor(() => expect(first.result.current.isError).toBe(true))
    expect(invalidations).not.toHaveBeenCalled()
    await act(async () => { await first.result.current.refetch() })
    await waitFor(() => expect(invalidations).toHaveBeenCalledTimes(3))
    first.unmount()
    client.removeQueries({ queryKey: worldKeys.bootstrapStatus(1), exact: true })
    client.setQueryData(worldKeys.bootstrapStatus(1), job)
    const recreated = renderHook(() => useBootstrapStatus(1), options)
    expect(invalidations).toHaveBeenCalledTimes(6)
    recreated.unmount()

    const otherClient = createReadyClient()
    otherClient.setQueryData(worldKeys.bootstrapStatus(1), job)
    const otherInvalidations = vi.spyOn(otherClient, 'invalidateQueries')
    const independent = renderHook(() => useBootstrapStatus(1), { wrapper: createQueryClientWrapper(otherClient) })
    expect(otherInvalidations).toHaveBeenCalledTimes(3)
    independent.unmount()
  })

  it('coordinates immediately completed triggers and a subsequent running job with mounted observers', async () => {
    const client = createReadyClient()
    client.setQueryData(worldKeys.bootstrapStatus(1), null)
    const invalidations = vi.spyOn(client, 'invalidateQueries')
    const view = renderHook(() => {
      useBootstrapStatus(1)
      useBootstrapStatus(1)
      return useTriggerBootstrap(1)
    }, { wrapper: createQueryClientWrapper(client) })
    vi.mocked(worldApi.triggerBootstrap).mockResolvedValueOnce(job)
    await act(async () => { await view.result.current.mutateAsync({ mode: 'initial' }) })
    await waitFor(() => expect(client.getQueryData(worldKeys.bootstrapStatus(1))).toEqual(job))
    expect(invalidations).toHaveBeenCalledTimes(3)

    vi.mocked(worldApi.triggerBootstrap).mockResolvedValueOnce({ ...job, job_id: 2, status: 'pending' })
    await act(async () => { await view.result.current.mutateAsync({ mode: 'reextract' }) })
    expect(invalidations).toHaveBeenCalledTimes(5)
    act(() => { client.setQueryData(worldKeys.bootstrapStatus(1), { ...job, job_id: 2 }) })
    await waitFor(() => expect(invalidations).toHaveBeenCalledTimes(8))
    view.unmount()
  })
})
