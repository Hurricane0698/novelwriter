import { describe, it, expect, vi, beforeEach } from 'vitest'
import { renderHook, act } from '@testing-library/react'
import { worldKeys } from '@/hooks/world/keys'
import { createQueryClientWrapper, createTestQueryClient } from './helpers'
import { LABELS } from '@/constants/labels'

const toastMock = vi.hoisted(() => vi.fn())
vi.mock('@/components/world-model/shared/useToast', () => ({
  useToast: () => ({ toast: toastMock }),
}))

vi.mock('@/services/api', () => ({
  worldApi: {
    updateSystem: vi.fn(),
  },
}))

import { worldApi } from '@/services/api'
import { useUpdateSystem } from '@/hooks/world/useSystems'

const mockUpdateSystem = worldApi.updateSystem as ReturnType<typeof vi.fn>

describe('useUpdateSystem', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('optimistically patches both system list + system detail without touching non-list keys', async () => {
    const novelId = 7
    const systemId = 13

    const listKey = [...worldKeys.systems(novelId), undefined]
    const detailKey = worldKeys.system(novelId, systemId)

    const initialList = [{
      id: systemId,
      novel_id: novelId,
      name: '旧体系',
      display_type: 'list',
      description: '',
      data: { items: [] },
      constraints: [],
      visibility: 'active',
      origin: 'manual',
      worldpack_pack_id: null,
      status: 'confirmed',
      created_at: '2026-02-01T00:00:00Z',
      updated_at: '2026-02-01T00:00:00Z',
    }]

    const initialDetail = initialList[0]

    const payload = { visibility: 'hidden' as const }
    const serverSystem = {
      ...initialDetail,
      visibility: payload.visibility,
      updated_at: '2026-02-02T00:00:00Z',
    }

    let resolveUpdate: (v: typeof serverSystem) => void
    const updatePromise = new Promise<typeof serverSystem>((resolve) => {
      resolveUpdate = resolve
    })
    mockUpdateSystem.mockReturnValue(updatePromise)

    const queryClient = createTestQueryClient()
    queryClient.setQueryData(listKey, initialList)
    queryClient.setQueryData(detailKey, initialDetail)

    const { result } = renderHook(() => useUpdateSystem(novelId), {
      wrapper: createQueryClientWrapper(queryClient),
    })

    let mutationPromise: Promise<unknown>
    act(() => {
      mutationPromise = result.current.mutateAsync({ systemId, data: payload })
    })

    await act(async () => { await Promise.resolve() })

    expect(mockUpdateSystem).toHaveBeenCalledWith(novelId, systemId, payload)
    expect(queryClient.getQueryData(detailKey)).toMatchObject({ visibility: payload.visibility })
    expect(queryClient.getQueryData(listKey)).toMatchObject([{ id: systemId, visibility: payload.visibility }])

    resolveUpdate!(serverSystem)
    await act(async () => { await mutationPromise })

    expect(queryClient.getQueryData(detailKey)).toMatchObject({ visibility: payload.visibility, updated_at: serverSystem.updated_at })
    expect(queryClient.getQueryData(listKey)).toMatchObject([{ id: systemId, visibility: payload.visibility, updated_at: serverSystem.updated_at }])
  })

  it('rolls back caches and shows a toast on update error', async () => {
    const novelId = 7
    const systemId = 13

    const listKeyAll = [...worldKeys.systems(novelId), undefined]
    const listKeyDisplay = [...worldKeys.systems(novelId), { display_type: 'list' }]
    const detailKey = worldKeys.system(novelId, systemId)

    const initialSystem = {
      id: systemId,
      novel_id: novelId,
      name: '旧体系',
      display_type: 'list',
      description: '',
      data: { items: [] },
      constraints: [],
      visibility: 'active',
      origin: 'manual',
      worldpack_pack_id: null,
      status: 'confirmed',
      created_at: '2026-02-01T00:00:00Z',
      updated_at: '2026-02-01T00:00:00Z',
    }

    const initialList = [initialSystem]
    const initialDetail = initialSystem

    const payload = { visibility: 'hidden' as const }

    let rejectUpdate: (e: unknown) => void
    const updatePromise = new Promise((_resolve, reject) => {
      rejectUpdate = reject
    })
    mockUpdateSystem.mockReturnValue(updatePromise)

    const queryClient = createTestQueryClient()
    queryClient.setQueryData(listKeyAll, initialList)
    queryClient.setQueryData(listKeyDisplay, initialList)
    queryClient.setQueryData(detailKey, initialDetail)

    const { result } = renderHook(() => useUpdateSystem(novelId), {
      wrapper: createQueryClientWrapper(queryClient),
    })

    let mutationPromise: Promise<unknown>
    act(() => {
      mutationPromise = result.current.mutateAsync({ systemId, data: payload })
    })

    await act(async () => { await Promise.resolve() })

    expect(queryClient.getQueryData(detailKey)).toMatchObject({ visibility: payload.visibility })
    expect(queryClient.getQueryData(listKeyAll)).toMatchObject([{ id: systemId, visibility: payload.visibility }])
    expect(queryClient.getQueryData(listKeyDisplay)).toMatchObject([{ id: systemId, visibility: payload.visibility }])

    rejectUpdate!(new Error('update failed'))
    await act(async () => {
      await expect(mutationPromise!).rejects.toThrow('update failed')
    })

    expect(queryClient.getQueryData(detailKey)).toEqual(initialDetail)
    expect(queryClient.getQueryData(listKeyAll)).toEqual(initialList)
    expect(queryClient.getQueryData(listKeyDisplay)).toEqual(initialList)
    expect(toastMock).toHaveBeenCalledWith(LABELS.ERROR_SAVE_FAILED)
  })
})
