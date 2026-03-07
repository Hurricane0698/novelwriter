import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { createElement } from 'react'
import { MemoryRouter } from 'react-router-dom'
import { ToastProvider } from '@/components/world-model/shared/Toast'
import { WorldBuildSection } from '@/components/world-model/shared/WorldBuildSection'
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

function renderSection() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return render(
    createElement(
      MemoryRouter,
      null,
      createElement(
        QueryClientProvider,
        { client: qc },
        createElement(ToastProvider, null, createElement(WorldBuildSection, { novelId: 1 }))
      )
    )
  )
}

describe('WorldBuildSection', () => {
  const mutateFn = vi.fn()

  beforeEach(() => {
    vi.restoreAllMocks()
    mockUseTriggerBootstrap.mockReturnValue({ mutate: mutateFn, isPending: false })
  })

  it('renders generation entry + bootstrap action rows', async () => {
    mockUseBootstrapStatus.mockReturnValue({ data: null, isLoading: false })
    const { rerender } = renderSection()

    expect(screen.getByText('构建世界观')).toBeTruthy()
    expect(screen.getByText('从设定文本生成')).toBeTruthy()
    expect(screen.getByText('从章节提取')).toBeTruthy()

    // Running
    mockUseBootstrapStatus.mockReturnValue({
      data: { ...baseJob, status: 'extracting' as const, progress: { step: 2, detail: 'Extracting...' } },
      isLoading: false,
    })
    rerender(
      createElement(
        MemoryRouter,
        null,
        createElement(
          QueryClientProvider,
          { client: new QueryClient({ defaultOptions: { queries: { retry: false } } }) },
          createElement(ToastProvider, null, createElement(WorldBuildSection, { novelId: 1 }))
        )
      )
    )
    expect(screen.getByText('提取候选词')).toBeTruthy()

    // Completed
    mockUseBootstrapStatus.mockReturnValue({ data: baseJob, isLoading: false })
    rerender(
      createElement(
        MemoryRouter,
        null,
        createElement(
          QueryClientProvider,
          { client: new QueryClient({ defaultOptions: { queries: { retry: false } } }) },
          createElement(ToastProvider, null, createElement(WorldBuildSection, { novelId: 1 }))
        )
      )
    )
    expect(screen.getByText('从章节提取')).toBeTruthy()
    expect(screen.getByText('10 实体 · 5 关系')).toBeTruthy()
  })
})
