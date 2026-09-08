import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { act, cleanup, renderHook } from '@testing-library/react'
import {
  collectInvalidateQueryKeysForAppliedSuggestions,
  useNovelCopilotRuns,
  useNovelCopilotRunsState,
} from '@/hooks/novel-copilot/useNovelCopilotRuns'
import { createQueryClientWrapper } from '@/__tests__/support/queryClient'
import { copilotApi } from '@/services/api'
import type { CopilotRun, NovelCopilotSession } from '@/types/copilot'

vi.mock('@/services/api', async (importOriginal) => ({
  ...await importOriginal<typeof import('@/services/api')>(),
  copilotApi: { listRuns: vi.fn(), pollRun: vi.fn() },
}))
vi.mock('@/contexts/UiLocaleContext', () => ({ useUiLocale: () => ({ t: translate }) }))
vi.mock('@/components/world-model/shared/useToast', () => ({ useToast: () => ({ toast: vi.fn() }) }))

const translate = (key: string) => key

function deferred<T>() {
  let resolve!: (value: T) => void
  let reject!: (reason: unknown) => void
  const promise = new Promise<T>((res, rej) => { resolve = res; reject = rej })
  return { promise, resolve, reject }
}

const session: NovelCopilotSession = {
  sessionId: 'local-session', signature: 'signature', novelId: 1,
  backendSessionId: 'backend-session', displayTitle: 'Research', interactionLocale: 'zh',
  prefill: { mode: 'research', scope: 'whole_book' },
}
const runningRun: CopilotRun = {
  run_id: 'run-1', status: 'running', prompt: 'Research', trace: [], evidence: [], suggestions: [],
}
const resolveBackendSessionId = async () => session.backendSessionId!

function renderRuns(strict = false) {
  return renderHook(({ sessions }: { sessions: NovelCopilotSession[] }) => {
    const state = useNovelCopilotRunsState(sessions)
    return useNovelCopilotRuns({
      ...state, sessions, focusedSessionId: sessions[0]?.sessionId ?? null, resolveBackendSessionId,
    })
  }, {
    initialProps: { sessions: [session] },
    wrapper: createQueryClientWrapper(),
    reactStrictMode: strict,
  })
}

describe('Copilot polling lifecycle', () => {
  beforeEach(() => {
    vi.useFakeTimers()
    vi.mocked(copilotApi.listRuns).mockReset().mockResolvedValue([runningRun])
    vi.mocked(copilotApi.pollRun).mockReset().mockResolvedValue(runningRun)
  })
  afterEach(() => {
    cleanup()
    vi.useRealTimers()
  })

  it.each(['resolve', 'reject'] as const)('does not restart polling when an in-flight request %s after unmount', async (outcome) => {
    const pending = deferred<CopilotRun>()
    vi.mocked(copilotApi.pollRun).mockReturnValueOnce(pending.promise)
    const view = renderRuns()
    await act(async () => { await Promise.resolve() })
    await act(async () => { await vi.advanceTimersByTimeAsync(1500) })
    expect(copilotApi.pollRun).toHaveBeenCalledTimes(1)

    view.unmount()
    expect(vi.mocked(copilotApi.pollRun).mock.calls[0][3]?.aborted).toBe(true)
    await act(async () => {
      if (outcome === 'resolve') pending.resolve(runningRun)
      else pending.reject(new Error('connection interrupted'))
      await Promise.resolve()
    })
    await act(async () => { await vi.advanceTimersByTimeAsync(60_000) })
    expect(copilotApi.pollRun).toHaveBeenCalledTimes(1)
  })

  it('hydrates and commits a completed poll after the StrictMode effect replay', async () => {
    vi.mocked(copilotApi.pollRun).mockResolvedValueOnce({ ...runningRun, status: 'completed' })
    const view = renderRuns(true)
    await act(async () => { await Promise.resolve() })
    expect(view.result.current.activeRun).toMatchObject({ run_id: 'run-1', status: 'running' })
    await act(async () => { await vi.advanceTimersByTimeAsync(1500) })
    expect(view.result.current.activeRun).toMatchObject({ run_id: 'run-1', status: 'completed' })
    await act(async () => { await vi.advanceTimersByTimeAsync(60_000) })
    expect(copilotApi.pollRun).toHaveBeenCalledTimes(1)
  })

  it('does not let a removed session response stop polling its replacement', async () => {
    const pending = deferred<CopilotRun>()
    vi.mocked(copilotApi.pollRun).mockReturnValueOnce(pending.promise)
    const view = renderRuns()
    await act(async () => { await Promise.resolve() })
    await act(async () => { await vi.advanceTimersByTimeAsync(1500) })

    view.rerender({ sessions: [] })
    const nextRun = { ...runningRun, run_id: 'run-2' }
    vi.mocked(copilotApi.listRuns).mockResolvedValueOnce([nextRun])
    vi.mocked(copilotApi.pollRun).mockResolvedValueOnce({ ...nextRun, status: 'completed' })
    view.rerender({ sessions: [{ ...session, backendSessionId: 'replacement-session' }] })
    await act(async () => { await Promise.resolve() })
    expect(view.result.current.activeRun?.run_id).toBe('run-2')

    await act(async () => { pending.resolve({ ...runningRun, status: 'completed' }); await Promise.resolve() })
    await act(async () => { await vi.advanceTimersByTimeAsync(1500) })
    expect(copilotApi.pollRun).toHaveBeenCalledTimes(2)
    expect(view.result.current.activeRun).toMatchObject({ run_id: 'run-2', status: 'completed' })
  })
})

describe('collectInvalidateQueryKeysForAppliedSuggestions', () => {
  it('invalidates only the touched world-model query families', () => {
    const suggestions = [
      {
        suggestion_id: 'sg_entity',
        kind: 'update_entity',
        title: '',
        summary: '',
        evidence_ids: [],
        target: { resource: 'entity', resource_id: 101, label: '苏瑶', tab: 'entities', entity_id: 101 },
        preview: { target_label: '', summary: '', field_deltas: [], evidence_quotes: [], actionable: true },
        apply: { type: 'update_entity', entity_id: 101, data: { description: 'x' } },
        status: 'pending',
      },
      {
        suggestion_id: 'sg_rel',
        kind: 'create_relationship',
        title: '',
        summary: '',
        evidence_ids: [],
        target: { resource: 'relationship', resource_id: null, label: '苏瑶 → 宗门', tab: 'relationships' },
        preview: { target_label: '', summary: '', field_deltas: [], evidence_quotes: [], actionable: true },
        apply: { type: 'create_relationship', data: { source_id: 101, target_id: 202, label: '同门' } },
        status: 'pending',
      },
      {
        suggestion_id: 'sg_system',
        kind: 'update_system',
        title: '',
        summary: '',
        evidence_ids: [],
        target: { resource: 'system', resource_id: 303, label: '宗门戒律', tab: 'systems' },
        preview: { target_label: '', summary: '', field_deltas: [], evidence_quotes: [], actionable: true },
        apply: { type: 'update_system', system_id: 303, data: { description: 'y' } },
        status: 'pending',
      },
    ] satisfies CopilotRun['suggestions']

    expect(collectInvalidateQueryKeysForAppliedSuggestions(9, suggestions)).toEqual([
      ['world', 9, 'entities'],
      ['world', 9, 'entities', 101],
      ['world', 9, 'relationships'],
      ['world', 9, 'systems'],
      ['world', 9, 'systems', 303],
    ])
  })
})
