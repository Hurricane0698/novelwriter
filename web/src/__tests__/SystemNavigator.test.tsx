import { beforeEach, describe, expect, it, vi } from 'vitest'
import type { ReactNode } from 'react'
import { render, screen } from '@testing-library/react'
import { UiLocaleProvider } from '@/contexts/UiLocaleContext'
import { SystemNavigator } from '@/components/atlas/systems/SystemNavigator'

const mockUseWorldSystems = vi.fn()
const mockUseCreateSystem = vi.fn()
const mockUseUpdateSystem = vi.fn()
const mockUseDeleteSystem = vi.fn()
const mockUseConfirmSystems = vi.fn()
const mockUseRejectSystems = vi.fn()

vi.mock('@/hooks/world/useSystems', () => ({
  useWorldSystems: (...args: unknown[]) => mockUseWorldSystems(...args),
  useCreateSystem: (...args: unknown[]) => mockUseCreateSystem(...args),
  useUpdateSystem: (...args: unknown[]) => mockUseUpdateSystem(...args),
  useDeleteSystem: (...args: unknown[]) => mockUseDeleteSystem(...args),
  useConfirmSystems: (...args: unknown[]) => mockUseConfirmSystems(...args),
  useRejectSystems: (...args: unknown[]) => mockUseRejectSystems(...args),
}))

vi.mock('@/components/atlas/review/DraftReviewSummaryCard', () => ({
  DraftReviewSummaryCard: () => <div data-testid="draft-review-summary" />,
}))

vi.mock('@/components/ui/glass-surface', () => ({
  GlassSurface: ({ children }: { children: ReactNode }) => <div>{children}</div>,
}))

function renderNavigator() {
  localStorage.setItem('novwr_ui_locale', 'zh')
  document.documentElement.lang = 'zh-CN'

  return render(
    <UiLocaleProvider>
      <SystemNavigator
        novelId={7}
        selectedId={9}
        onSelect={vi.fn()}
        onOpenDraftReview={vi.fn()}
      />
    </UiLocaleProvider>,
  )
}

describe('SystemNavigator', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    Object.defineProperty(HTMLElement.prototype, 'scrollIntoView', {
      configurable: true,
      value: vi.fn(),
    })
    mockUseWorldSystems.mockReturnValue({
      data: [
        {
          id: 9,
          name: '修真体系',
          description: '',
          display_type: 'hierarchy',
          status: 'confirmed',
          visibility: 'active',
          constraints: [],
          created_at: '2026-03-01T00:00:00Z',
        },
      ],
    })
    mockUseCreateSystem.mockReturnValue({ mutate: vi.fn(), isPending: false })
    mockUseUpdateSystem.mockReturnValue({ mutate: vi.fn(), isPending: false })
    mockUseDeleteSystem.mockReturnValue({ mutate: vi.fn(), isPending: false })
    mockUseConfirmSystems.mockReturnValue({ mutate: vi.fn(), isPending: false })
    mockUseRejectSystems.mockReturnValue({ mutate: vi.fn(), isPending: false })
  })

  it('keeps only concise review metadata in the footer after the atlas assist split', () => {
    renderNavigator()

    expect(screen.getByTestId('draft-review-summary')).toBeInTheDocument()
    expect(screen.queryByTestId('world-build-panel')).not.toBeInTheDocument()
  })
})
