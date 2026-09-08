import type { ReactNode } from 'react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { MemoryRouter, Route, Routes, useLocation, useNavigate } from 'react-router-dom'
import { UiLocaleProvider } from '@/contexts/UiLocaleContext'
import { NovelShell } from '@/components/novel-shell/NovelShell'
import { useNovelCopilot } from '@/components/novel-copilot/NovelCopilotContext'
import { useNovelShell } from '@/components/novel-shell/NovelShellContext'
import { NovelAtlasPage } from '@/pages/NovelAtlasPage'

const ACTIVE_PENDING_STARTED_AT = Date.parse('2026-03-30T00:00:30Z')
const ACTIVE_PENDING_NOW_MS = Date.parse('2026-03-30T00:10:00Z')

const mockUseWorldEntities = vi.fn()
const mockUseWorldRelationships = vi.fn()
const mockUseWorldSystems = vi.fn()
const mockUseBootstrapStatus = vi.fn()
const mockGetNovel = vi.fn()

vi.mock('@/components/atlas/AtlasShell', () => ({
  AtlasShell: ({ children }: { children: ReactNode }) => <div>{children}</div>,
}))

vi.mock('@/components/ui/glass-surface', () => ({
  GlassSurface: ({ children }: { children: ReactNode }) => <div>{children}</div>,
}))

vi.mock('@/components/novel-copilot/NovelCopilotDrawer', () => ({
  NovelCopilotDrawer: () => <div data-testid="novel-copilot-drawer" />,
}))

vi.mock('@/components/atlas/workbench/AtlasAssistWorkbench', () => ({
  AtlasAssistWorkbench: ({
    onOpenDraftReview,
    width,
    presentation,
  }: {
    onOpenDraftReview?: (kind?: 'entities' | 'relationships' | 'systems') => void
    width?: number
    presentation?: 'rail' | 'overlay'
  }) => (
    <div
      data-testid="atlas-assist-workbench"
      data-width={width}
      data-presentation={presentation ?? 'rail'}
    >
      <button
        type="button"
        data-testid="atlas-assist-open-review"
        onClick={() => onOpenDraftReview?.('entities')}
      >
        open review
      </button>
    </div>
  ),
}))

vi.mock('@/components/atlas/entities/EntityNavigator', () => ({
  EntityNavigator: ({
    selectedEntityId,
    onSelectEntity,
    bottomSlot,
  }: {
    selectedEntityId: number | null
    onSelectEntity: (id: number) => void
    bottomSlot?: ReactNode
  }) => (
    <div>
      <div data-testid="entity-navigator-selection">{selectedEntityId ?? 'none'}</div>
      <button type="button" onClick={() => onSelectEntity(10)}>
        选择实体10
      </button>
      <div data-testid="entity-navigator-bottom-slot">{bottomSlot}</div>
    </div>
  ),
}))

vi.mock('@/components/world-model/entities/EntityDetail', () => ({
  EntityDetail: ({ entityId }: { entityId: number | null }) => (
    <div data-testid="entity-detail">{entityId ?? 'none'}</div>
  ),
}))

vi.mock('@/components/atlas/systems/SystemsWorkspace', () => ({
  SystemsWorkspace: () => <div data-testid="systems-workspace" />,
}))

vi.mock('@/components/world-model/relationships/RelationshipsTab', () => ({
  RelationshipsTab: ({ selectedRelationshipId }: { selectedRelationshipId?: number | null }) => (
    <div data-testid="relationships-tab">{selectedRelationshipId ?? 'none'}</div>
  ),
}))

vi.mock('@/components/world-model/shared/DraftReviewTab', () => ({
  DraftReviewTab: ({ highlightId }: { highlightId?: number | null }) => (
    <div data-testid="draft-review-tab">{highlightId ?? 'none'}</div>
  ),
}))

vi.mock('@/components/atlas/review/DraftReviewSummaryCard', () => ({
  DraftReviewSummaryCard: () => <div data-testid="draft-review-summary" />,
}))

vi.mock('@/components/atlas/review/DraftReviewNavigator', () => ({
  DraftReviewNavigator: ({ activeItemId }: { activeItemId?: number | null }) => (
    <div data-testid="draft-review-navigator">{activeItemId ?? 'none'}</div>
  ),
}))

vi.mock('@/components/atlas/relationships/RelationshipSidebarPanel', () => ({
  RelationshipSidebarPanel: () => <div data-testid="relationship-sidebar-panel" />,
}))

vi.mock('@/hooks/world/useEntities', () => ({
  useWorldEntities: (...args: unknown[]) => mockUseWorldEntities(...args),
}))

vi.mock('@/hooks/world/useRelationships', () => ({
  useWorldRelationships: (...args: unknown[]) => mockUseWorldRelationships(...args),
}))

vi.mock('@/hooks/world/useSystems', () => ({
  useWorldSystems: (...args: unknown[]) => mockUseWorldSystems(...args),
}))

vi.mock('@/hooks/world/useBootstrap', () => ({
  useBootstrapStatus: (...args: unknown[]) => mockUseBootstrapStatus(...args),
}))

vi.mock('@/services/api', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@/services/api')>()
  return {
    ...actual,
    api: {
      ...actual.api,
      getNovel: (...args: unknown[]) => mockGetNovel(...args),
    },
  }
})

function LocationProbe() {
  const location = useLocation()
  return <div data-testid="location-search">{location.search}</div>
}

function HistoryBackProbe() {
  const navigate = useNavigate()
  return (
    <button type="button" data-testid="history-back" onClick={() => navigate(-1)}>
      back
    </button>
  )
}

function CopilotStateProbe() {
  const { isOpen } = useNovelCopilot()
  const { shellState } = useNovelShell()

  return (
    <>
      <div data-testid="copilot-open-state">{isOpen ? 'open' : 'closed'}</div>
      <div data-testid="copilot-drawer-width">{shellState.drawerWidth}</div>
    </>
  )
}

class ResizeObserverMock {
  observe() {}
  disconnect() {}
}

const originalResizeObserver = globalThis.ResizeObserver
const originalClientWidthDescriptor = Object.getOwnPropertyDescriptor(HTMLElement.prototype, 'clientWidth')

function renderWithShell(ui: ReactNode, initialEntry: string) {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } })

  return render(
    <QueryClientProvider client={queryClient}>
      <UiLocaleProvider>
        <MemoryRouter initialEntries={[initialEntry]}>
          {ui}
        </MemoryRouter>
      </UiLocaleProvider>
    </QueryClientProvider>,
  )
}

describe('NovelAtlasPage', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    vi.stubGlobal('ResizeObserver', ResizeObserverMock)
    Object.defineProperty(HTMLElement.prototype, 'clientWidth', {
      configurable: true,
      get() {
        return 1400
      },
    })
    localStorage.clear()
    document.documentElement.lang = 'zh-CN'
    mockUseWorldEntities.mockImplementation((_novelId: number, params?: { status?: string }) => ({
      data: params?.status === 'draft'
        ? []
        : [
            { id: 9, name: '苏瑶' },
            { id: 10, name: '韩立' },
          ],
      isSuccess: true,
    }))
    mockUseWorldRelationships.mockImplementation(() => ({
      data: [],
      isSuccess: true,
    }))
    mockUseWorldSystems.mockImplementation(() => ({
      data: [],
      isSuccess: true,
    }))
    mockUseBootstrapStatus.mockReturnValue({
      data: null,
      isLoading: false,
    })
    mockGetNovel.mockResolvedValue({
      id: 7,
      title: '测试小说',
      is_seeded_demo: false,
      created_at: '2026-03-01T00:00:00Z',
    })
  })

  afterEach(() => {
    if (originalResizeObserver) {
      vi.stubGlobal('ResizeObserver', originalResizeObserver)
    } else {
      vi.unstubAllGlobals()
    }

    if (originalClientWidthDescriptor) {
      Object.defineProperty(HTMLElement.prototype, 'clientWidth', originalClientWidthDescriptor)
    } else {
      delete (HTMLElement.prototype as { clientWidth?: number }).clientWidth
    }
  })

  it('hydrates entity selection from the atlas URL and keeps later selections in the URL contract', async () => {
    const user = userEvent.setup()

    renderWithShell(
      <>
        <Routes>
          <Route element={<NovelShell />}>
            <Route
              path="/world/:novelId"
              element={(
                <>
                  <NovelAtlasPage />
                  <LocationProbe />
                </>
              )}
            />
          </Route>
        </Routes>
      </>,
      '/world/7?tab=entities&entity=9',
    )

    expect(await screen.findByTestId('entity-detail')).toHaveTextContent('9')
    expect(screen.getByTestId('entity-navigator-selection')).toHaveTextContent('9')

    await user.click(screen.getByRole('button', { name: '选择实体10' }))

    expect(await screen.findByTestId('entity-detail')).toHaveTextContent('10')
    expect(screen.getByTestId('location-search')).toHaveTextContent('entity=10')
  })

  it('keeps navigator footers free of the old world-build card and mounts an independent assist workbench', async () => {
    renderWithShell(
      <>
        <Routes>
          <Route element={<NovelShell />}>
            <Route path="/world/:novelId" element={<NovelAtlasPage />} />
          </Route>
        </Routes>
      </>,
      '/world/7?tab=entities&entity=9',
    )

    expect(await screen.findByTestId('atlas-assist-workbench')).toBeInTheDocument()
    expect(screen.getByTestId('entity-navigator-bottom-slot')).toContainElement(
      screen.getByTestId('draft-review-summary'),
    )
    expect(screen.queryByTestId('world-build-panel')).not.toBeInTheDocument()
  })

  it('hydrates relationship highlight from the atlas URL for copilot target navigation', () => {
    renderWithShell(
      <>
        <Routes>
          <Route element={<NovelShell />}>
            <Route path="/world/:novelId" element={<NovelAtlasPage />} />
          </Route>
        </Routes>
      </>,
      '/world/7?tab=relationships&entity=9&relationship=21',
    )

    expect(screen.getByTestId('relationships-tab')).toHaveTextContent('21')
  })

  it('hydrates review highlight from the atlas URL for copilot draft targets', async () => {
    renderWithShell(
      <>
        <Routes>
          <Route element={<NovelShell />}>
            <Route path="/world/:novelId" element={<NovelAtlasPage />} />
          </Route>
        </Routes>
      </>,
      '/world/7?tab=review&kind=relationships&highlight=31',
    )

    expect(await screen.findByTestId('draft-review-tab')).toHaveTextContent('31')
    expect(await screen.findByTestId('draft-review-navigator')).toHaveTextContent('31')
  })

  it('opens atlas review as a browser-backable history step while keeping handoff params in the previous URL', async () => {
    const user = userEvent.setup()
    mockUseWorldEntities.mockImplementation((_novelId: number, params?: { status?: string }) => ({
      data: params?.status === 'draft'
        ? [{ id: 101, name: '待审核实体' }]
        : [
            { id: 9, name: '苏瑶' },
            { id: 10, name: '韩立' },
          ],
      isSuccess: true,
    }))
    mockUseWorldSystems.mockImplementation((_novelId: number, params?: { status?: string }) => ({
      data: params?.status === 'draft' ? [{ id: 201, name: '待审核体系' }] : [],
      isSuccess: true,
    }))

    renderWithShell(
      <>
        <Routes>
          <Route element={<NovelShell />}>
            <Route
              path="/world/:novelId"
              element={(
                <>
                  <NovelAtlasPage />
                  <LocationProbe />
                  <HistoryBackProbe />
                </>
              )}
            />
          </Route>
        </Routes>
      </>,
      '/world/7?tab=entities&entity=9&worldEntryHandoff=generate_review&worldEntryEntities=1&worldEntrySystems=1',
    )

    expect(screen.getByTestId('location-search')).toHaveTextContent('tab=entities')
    expect(screen.getByTestId('location-search')).toHaveTextContent('worldEntryHandoff=generate_review')

    await user.click(await screen.findByTestId('atlas-assist-open-review'))

    expect(screen.getByTestId('location-search')).toHaveTextContent('tab=review')
    expect(screen.getByTestId('location-search')).toHaveTextContent('kind=entities')

    await user.click(screen.getByTestId('history-back'))

    expect(screen.getByTestId('location-search')).toHaveTextContent('tab=entities')
    expect(screen.getByTestId('location-search')).toHaveTextContent('worldEntryHandoff=generate_review')
  })

  it('normalizes stale review handoffs back to success once Atlas resolves that no draft backlog remains', async () => {
    renderWithShell(
      <>
        <Routes>
          <Route element={<NovelShell />}>
            <Route
              path="/world/:novelId"
              element={(
                <>
                  <NovelAtlasPage />
                  <LocationProbe />
                </>
              )}
            />
          </Route>
        </Routes>
      </>,
      '/world/7?tab=entities&worldEntryHandoff=generate_review&worldEntryEntities=7&worldEntryRelationships=6&worldEntrySystems=2',
    )

    await waitFor(() => {
      expect(screen.getByTestId('location-search')).toHaveTextContent('worldEntryHandoff=generate_success')
    })
    expect(screen.getByTestId('location-search')).not.toHaveTextContent('worldEntryHandoff=generate_review')
    expect(screen.getByTestId('location-search')).toHaveTextContent('worldEntryEntities=7')
    expect(screen.getByTestId('location-search')).toHaveTextContent('worldEntryRelationships=6')
    expect(screen.getByTestId('location-search')).toHaveTextContent('worldEntrySystems=2')
  })

  it('upgrades a pending extraction marker into a terminal handoff when Atlas mounts after async completion', async () => {
    const dateNowSpy = vi.spyOn(Date, 'now').mockReturnValue(ACTIVE_PENDING_NOW_MS)
    mockUseWorldEntities.mockImplementation((_novelId: number, params?: { status?: string }) => ({
      data: params?.status === 'draft'
        ? [{ id: 101, name: '待审核实体' }, { id: 102, name: '待审核实体2' }]
        : [
            { id: 9, name: '苏瑶' },
            { id: 10, name: '韩立' },
          ],
      isSuccess: true,
    }))
    mockUseWorldRelationships.mockImplementation((_novelId: number, params?: { status?: string }) => ({
      data: params?.status === 'draft' ? [{ id: 301, label: '关联' }] : [],
      isSuccess: true,
    }))
    mockUseBootstrapStatus.mockReturnValue({
      data: {
        job_id: 41,
        novel_id: 7,
        mode: 'initial',
        initialized: true,
        status: 'completed',
        progress: { step: 5, detail: '完成' },
        result: {
          entities_found: 2,
          relationships_found: 1,
          index_refresh_only: false,
        },
        error: null,
        created_at: '2026-03-30T00:00:00Z',
        updated_at: '2026-03-30T00:01:00Z',
      },
      isLoading: false,
    })

    renderWithShell(
      <>
        <Routes>
          <Route element={<NovelShell />}>
            <Route
              path="/world/:novelId"
              element={(
                <>
                  <NovelAtlasPage />
                  <LocationProbe />
                </>
              )}
            />
          </Route>
        </Routes>
      </>,
      `/world/7?tab=entities&worldEntryPending=extract&worldEntryPendingAt=${ACTIVE_PENDING_STARTED_AT}`,
    )

    await waitFor(() => {
      expect(screen.getByTestId('location-search')).toHaveTextContent('worldEntryHandoff=extract_review')
    })
    expect(screen.getByTestId('location-search')).toHaveTextContent('worldEntryEntities=2')
    expect(screen.getByTestId('location-search')).toHaveTextContent('worldEntryRelationships=1')
    expect(screen.getByTestId('location-search')).not.toHaveTextContent('worldEntryPending=')
    dateNowSpy.mockRestore()
  })

  it('clears expired pending extraction markers after reload so Atlas does not stay stuck in running attention forever', async () => {
    const dateNowSpy = vi.spyOn(Date, 'now').mockReturnValue(Date.parse('2026-03-31T01:00:00Z'))

    mockUseBootstrapStatus.mockReturnValue({
      data: null,
      isLoading: false,
    })

    renderWithShell(
      <>
        <Routes>
          <Route element={<NovelShell />}>
            <Route
              path="/world/:novelId"
              element={(
                <>
                  <NovelAtlasPage />
                  <LocationProbe />
                </>
              )}
            />
          </Route>
        </Routes>
      </>,
      '/world/7?tab=entities&worldEntryPending=extract&worldEntryPendingAt=1743375600000',
    )

    await waitFor(() => {
      expect(screen.getByTestId('location-search')).not.toHaveTextContent('worldEntryPending=')
    })

    dateNowSpy.mockRestore()
  })

  it('returns to the structured studio origin without relying on raw returnTo', async () => {
    const user = userEvent.setup()

    renderWithShell(
      <>
        <Routes>
          <Route element={<NovelShell />}>
            <Route
              path="/world/:novelId"
              element={<NovelAtlasPage />}
            />
            <Route
              path="/novel/:novelId"
              element={<LocationProbe />}
            />
          </Route>
        </Routes>
      </>,
      '/world/7?tab=entities&entity=9&originStage=results&originChapter=3&originResultsChapter=3&originResultsContinuations=0:15,1:16&originResultsTotalVariants=2&originArtifactPanel=injection_summary&originSummaryCategory=entities',
    )

    await user.click(screen.getByRole('button', { name: '返回工作台' }))

    expect(screen.getByTestId('location-search')).toHaveTextContent('stage=results')
    expect(screen.getByTestId('location-search')).toHaveTextContent('chapter=3')
    expect(screen.getByTestId('location-search')).toHaveTextContent('continuations=0%3A15%2C1%3A16')
    expect(screen.getByTestId('location-search')).toHaveTextContent('artifactPanel=injection_summary')
  })

  it('uses the same return-to-studio control as a safe fallback when atlas has no origin state', async () => {
    const user = userEvent.setup()

    renderWithShell(
      <>
        <Routes>
          <Route element={<NovelShell />}>
            <Route path="/world/:novelId" element={<NovelAtlasPage />} />
            <Route path="/novel/:novelId" element={<LocationProbe />} />
          </Route>
        </Routes>
      </>,
      '/world/7?tab=entities&entity=9',
    )

    await user.click(screen.getByRole('button', { name: '返回工作台' }))

    expect(screen.getByTestId('location-search')).toBeEmptyDOMElement()
  })

  it('renders the atlas chrome in English when the UI locale is en', () => {
    localStorage.setItem('novwr_ui_locale', 'en')
    document.documentElement.lang = 'en'

    renderWithShell(
      <>
        <Routes>
          <Route element={<NovelShell />}>
            <Route path="/world/:novelId" element={<NovelAtlasPage />} />
          </Route>
        </Routes>
      </>,
      '/world/7?tab=review',
    )

    expect(screen.getByRole('button', { name: 'Return to Studio' })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Draft review' })).toBeInTheDocument()
  })

  it('keeps the atlas assist zone mounted on narrow desktops by shrinking it to the available width first', async () => {
    Object.defineProperty(HTMLElement.prototype, 'clientWidth', {
      configurable: true,
      get() {
        return 1100
      },
    })

    renderWithShell(
      <>
        <Routes>
          <Route element={<NovelShell />}>
            <Route
              path="/world/:novelId"
              element={(
                <>
                  <NovelAtlasPage />
                  <CopilotStateProbe />
                </>
              )}
            />
          </Route>
        </Routes>
      </>,
      '/world/7?tab=entities',
    )

    expect(screen.getByTestId('copilot-open-state')).toHaveTextContent('closed')
    expect(await screen.findByTestId('atlas-assist-workbench')).toBeInTheDocument()
    expect(screen.getByTestId('atlas-assist-workbench')).toHaveAttribute('data-presentation', 'rail')
    expect(screen.getByTestId('atlas-assist-workbench')).toHaveAttribute('data-width', '340')
    expect(screen.getByTestId('copilot-drawer-width')).toHaveTextContent('340')
  })

  it('keeps Atlas assist reachable on medium desktops by switching it into overlay mode instead of unmounting it', async () => {
    Object.defineProperty(HTMLElement.prototype, 'clientWidth', {
      configurable: true,
      get() {
        return 1000
      },
    })

    renderWithShell(
      <>
        <Routes>
          <Route element={<NovelShell />}>
            <Route
              path="/world/:novelId"
              element={(
                <>
                  <NovelAtlasPage />
                  <CopilotStateProbe />
                </>
              )}
            />
          </Route>
        </Routes>
      </>,
      '/world/7?tab=entities',
    )

    expect(screen.getByTestId('copilot-open-state')).toHaveTextContent('closed')
    expect(await screen.findByTestId('atlas-assist-workbench')).toHaveAttribute('data-presentation', 'overlay')
  })

  it('lets the atlas header toggle collapse and reopen the independent assist zone', async () => {
    const user = userEvent.setup()

    renderWithShell(
      <>
        <Routes>
          <Route element={<NovelShell />}>
            <Route path="/world/:novelId" element={<NovelAtlasPage />} />
          </Route>
        </Routes>
      </>,
      '/world/7?tab=entities&entity=9',
    )

    expect(await screen.findByTestId('atlas-assist-workbench')).toBeInTheDocument()

    await user.click(screen.getByRole('button', { name: 'Toggle Copilot' }))
    expect(screen.queryByTestId('atlas-assist-workbench')).not.toBeInTheDocument()

    await user.click(screen.getByRole('button', { name: 'Toggle Copilot' }))
    expect(await screen.findByTestId('atlas-assist-workbench')).toBeInTheDocument()
  })
})
