import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { createElement } from 'react'
import { BootstrapPanel } from '@/components/world-model/shared/BootstrapPanel'
import { ToastProvider } from '@/components/world-model/shared/Toast'
import type { BootstrapJobResponse } from '@/types/api'

// Mock the hooks
const mockUseBootstrapStatus = vi.fn()
const mockUseTriggerBootstrap = vi.fn()

vi.mock('@/hooks/world/useBootstrap', () => ({
  useBootstrapStatus: (...args: unknown[]) => mockUseBootstrapStatus(...args),
  useTriggerBootstrap: (...args: unknown[]) => mockUseTriggerBootstrap(...args),
}))

const baseJob: BootstrapJobResponse = {
  job_id: 1,
  novel_id: 1,
  mode: 'index_refresh',
  initialized: true,
  status: 'completed',
  progress: { step: 5, detail: 'Done' },
  result: { entities_found: 10, relationships_found: 5, index_refresh_only: false },
  error: null,
  created_at: '2026-01-01T00:00:00Z',
  updated_at: '2026-01-01T00:00:00Z',
}

function renderPanel() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return render(
    createElement(
      QueryClientProvider,
      { client: qc },
      createElement(ToastProvider, null, createElement(BootstrapPanel, { novelId: 1 }))
    )
  )
}

describe('BootstrapPanel (sidebar variant)', () => {
  const mutateFn = vi.fn()

  beforeEach(() => {
    vi.restoreAllMocks()
    mockUseTriggerBootstrap.mockReturnValue({ mutate: mutateFn, isPending: false })
  })

  it('renders skeleton while loading', () => {
    mockUseBootstrapStatus.mockReturnValue({ data: undefined, isLoading: true })
    renderPanel()
    expect(document.querySelector('.animate-pulse')).toBeTruthy()
  })

  it('renders idle action row when no job exists', () => {
    mockUseBootstrapStatus.mockReturnValue({ data: null, isLoading: false })
    renderPanel()
    expect(screen.getByText('从章节提取')).toBeTruthy()
  })

  it('renders completed state with compact summary', () => {
    mockUseBootstrapStatus.mockReturnValue({ data: baseJob, isLoading: false })
    renderPanel()
    expect(screen.getByText('从章节提取')).toBeTruthy()
    expect(screen.getByText('10 实体 · 5 关系')).toBeTruthy()
  })

  it('uses legacy fallback and shows completed row when initialized field is missing', () => {
    const legacyJob = {
      ...baseJob,
      mode: 'reextract' as const,
    } as unknown as BootstrapJobResponse
    delete (legacyJob as unknown as { initialized?: boolean }).initialized

    mockUseBootstrapStatus.mockReturnValue({ data: legacyJob, isLoading: false })
    renderPanel()
    expect(screen.getByText('从章节提取')).toBeTruthy()
  })

  it('renders completed summary for index refresh only', () => {
    const refreshOnlyJob = {
      ...baseJob,
      result: { ...baseJob.result, entities_found: 0, relationships_found: 0, index_refresh_only: true },
    }
    mockUseBootstrapStatus.mockReturnValue({ data: refreshOnlyJob, isLoading: false })
    renderPanel()
    expect(screen.getByText('索引已刷新')).toBeTruthy()
  })

  it('renders failed state with retry hint', () => {
    const failedJob = { ...baseJob, status: 'failed' as const, error: 'timeout' }
    mockUseBootstrapStatus.mockReturnValue({ data: failedJob, isLoading: false })
    renderPanel()
    expect(screen.getByText(/执行失败/)).toBeTruthy()
    expect(screen.getByText(/重试/)).toBeTruthy()
  })

  it('renders running state with progress bar and step label', () => {
    const runningJob = { ...baseJob, status: 'extracting' as const, progress: { step: 2, detail: 'Extracting...' } }
    mockUseBootstrapStatus.mockReturnValue({ data: runningJob, isLoading: false })
    renderPanel()
    expect(screen.getByText('提取候选词')).toBeTruthy()
  })

  it('calls trigger with initial payload on idle row click', async () => {
    mockUseBootstrapStatus.mockReturnValue({ data: null, isLoading: false })
    renderPanel()

    await userEvent.click(screen.getByText('从章节提取'))
    expect(mutateFn).toHaveBeenCalledWith({ mode: 'initial' }, expect.any(Object))
  })

  it('shows confirm dialog on completed row click (reextract)', async () => {
    mockUseBootstrapStatus.mockReturnValue({ data: baseJob, isLoading: false })
    renderPanel()

    await userEvent.click(screen.getByText('从章节提取'))
    expect(screen.getByText('危险操作：重提取实体关系')).toBeTruthy()

    await userEvent.click(screen.getByText('确认重提取'))
    expect(mutateFn).toHaveBeenCalledWith(
      { mode: 'reextract', draft_policy: 'replace_bootstrap_drafts', force: true },
      expect.any(Object)
    )
  })

  it('disables action row when trigger is pending', () => {
    mockUseBootstrapStatus.mockReturnValue({ data: null, isLoading: false })
    mockUseTriggerBootstrap.mockReturnValue({ mutate: mutateFn, isPending: true })
    renderPanel()

    const row = screen.getByText('从章节提取').closest('button')
    expect(row?.disabled).toBe(true)
  })
})
