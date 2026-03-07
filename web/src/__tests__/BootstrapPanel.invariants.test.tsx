import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { createElement } from 'react'
import { BootstrapPanel } from '@/components/world-model/shared/BootstrapPanel'
import { ToastProvider } from '@/components/world-model/shared/Toast'
import type { BootstrapJobResponse } from '@/types/api'

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

describe('BootstrapPanel invariants', () => {
  const mutateFn = vi.fn()

  beforeEach(() => {
    vi.restoreAllMocks()
    mockUseTriggerBootstrap.mockReturnValue({ mutate: mutateFn, isPending: false })
  })

  it('BI-03 first-run primary CTA should be extraction, not index maintenance', () => {
    mockUseBootstrapStatus.mockReturnValue({ data: null, isLoading: false })
    renderPanel()

    expect(screen.getByText('从章节提取')).toBeTruthy()
    expect(screen.queryByText('刷新索引')).toBeNull()
  })

  it('BI-03 first-run primary CTA should trigger initial mode', async () => {
    mockUseBootstrapStatus.mockReturnValue({ data: null, isLoading: false })
    renderPanel()

    await userEvent.click(screen.getByText('从章节提取'))
    expect(mutateFn).toHaveBeenCalledWith({ mode: 'initial' }, expect.any(Object))
  })

  it('BI-03 post-initial state should not expose index-refresh as a primary visible action', () => {
    mockUseBootstrapStatus.mockReturnValue({ data: baseJob, isLoading: false })
    renderPanel()

    expect(screen.getByText('从章节提取')).toBeTruthy()
    expect(screen.queryByText('刷新索引')).toBeNull()
  })
})
