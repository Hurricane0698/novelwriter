import type { ComponentProps } from 'react'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { render, screen } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { UiLocaleProvider } from '@/contexts/UiLocaleContext'
import { StudioSupportRail } from '@/components/studio/rail/StudioSupportRail'

const ACTIVE_PENDING_STARTED_AT = 2_000_000_000_000
import type {
  WorldEntryHandoffState,
  WorldEntryPendingState,
} from '@/components/novel-shell/NovelShellRouteState'

vi.mock('@/components/world-model/shared/BootstrapPanel', () => ({
  BootstrapPanel: () => <div data-testid="bootstrap-panel" />,
}))

vi.mock('@/components/world-model/shared/WorldGenerationDialog', () => ({
  WorldGenerationDialog: () => null,
}))

function renderRail(overrides?: Partial<ComponentProps<typeof StudioSupportRail>>) {
  return render(
    <UiLocaleProvider>
      <MemoryRouter>
        <StudioSupportRail
          novelId={7}
          latestChapterReference="第 8 章"
          chapterCount={8}
          worldEntityCount={5}
          worldSystemCount={2}
          windowIndexStatus={{ text: '全书检索可用', tone: 'success', requiresFallback: false }}
          demoGuideState={{
            status: 'not_started',
            visited: {
              chapter: false,
              atlas: false,
              write: false,
              copilot: false,
            },
          }}
          demoGuideProgressCount={0}
          showDemoGuideExpanded={false}
          showDemoGuideReopen={false}
          onOpenDemoChapter={vi.fn()}
          onOpenDemoAtlas={vi.fn()}
          onOpenDemoWriteStage={vi.fn()}
          onOpenDemoCopilot={vi.fn()}
          onSkipDemoGuide={vi.fn()}
          onReopenDemoGuide={vi.fn()}
          onOpenWholeBookCopilot={vi.fn()}
          worldEntryHandoff={null as WorldEntryHandoffState | null}
          worldEntryPending={null as WorldEntryPendingState | null}
          onWorldEntryHandoffChange={vi.fn()}
          onOpenAtlas={vi.fn()}
          onOpenAtlasReview={vi.fn()}
          {...overrides}
        />
      </MemoryRouter>
    </UiLocaleProvider>,
  )
}

describe('StudioSupportRail', () => {
  beforeEach(() => {
    Object.defineProperty(HTMLElement.prototype, 'scrollIntoView', {
      configurable: true,
      value: vi.fn(),
    })
  })

  it('promotes world entry ahead of research when the novel still has no world data', () => {
    renderRail({
      worldEntityCount: 0,
      worldSystemCount: 0,
      windowIndexStatus: { text: '正在准备全书内容。', tone: 'muted', requiresFallback: false },
    })

    const sections = screen.getByTestId('studio-support-rail-sections')
    const panels = Array.from(sections.querySelectorAll('[data-testid="studio-world-entry-panel"], [data-testid="studio-research-panel"]'))
      .map((node) => node.getAttribute('data-testid'))

    expect(panels).toEqual(['studio-world-entry-panel', 'studio-research-panel'])
    expect(screen.getByTestId('studio-world-entry-panel')).toHaveAttribute('data-prominence', 'prominent')
    expect(screen.getByTestId('studio-assistant-rail')).toHaveAttribute('data-world-entry-stage', 'cold_start')
    expect(screen.queryByTestId('studio-world-entry-attention-banner')).not.toBeInTheDocument()
    expect(screen.getByTestId('novel-copilot-trigger')).toBeInTheDocument()
  })

  it('restores research ahead of compact world sync once world data exists', () => {
    renderRail()

    const sections = screen.getByTestId('studio-support-rail-sections')
    const panels = Array.from(sections.querySelectorAll('[data-testid="studio-world-entry-panel"], [data-testid="studio-research-panel"]'))
      .map((node) => node.getAttribute('data-testid'))

    expect(panels).toEqual(['studio-research-panel', 'studio-world-entry-panel'])
    expect(screen.getByTestId('studio-world-entry-panel')).toHaveAttribute('data-prominence', 'compact')
    expect(screen.getByTestId('studio-assistant-rail')).toHaveAttribute('data-world-entry-stage', 'routine')
    expect(screen.queryByTestId('studio-world-entry-attention-banner')).not.toBeInTheDocument()
    expect(screen.getByTestId('world-build-generate')).toBeInTheDocument()
  })

  it('temporarily re-elevates world entry ahead of research when review attention is pending', () => {
    const onOpenAtlasReview = vi.fn()
    renderRail({
      worldEntryHandoff: {
        kind: 'generate_review',
        entityCount: 1,
        relationshipCount: 0,
        systemCount: 1,
      },
      onOpenAtlasReview,
    })

    const sections = screen.getByTestId('studio-support-rail-sections')
    const panels = Array.from(sections.querySelectorAll('[data-testid="studio-world-entry-panel"], [data-testid="studio-research-panel"]'))
      .map((node) => node.getAttribute('data-testid'))

    expect(panels).toEqual(['studio-world-entry-panel', 'studio-research-panel'])
    expect(screen.getByTestId('studio-world-entry-panel')).toHaveAttribute('data-prominence', 'elevated')
    expect(screen.getByTestId('studio-assistant-rail')).toHaveAttribute('data-world-entry-stage', 'attention')
    expect(screen.getByTestId('studio-world-entry-attention-banner')).toHaveAttribute('data-tone', 'needs_review')
    screen.getByTestId('studio-world-entry-attention-action').click()
    expect(onOpenAtlasReview).toHaveBeenCalledWith('entities')
  })

  it('keeps world entry elevated while extraction is still pending in the URL-backed handoff state', () => {
    renderRail({
      worldEntryPending: {
        kind: 'extract',
        startedAtMs: ACTIVE_PENDING_STARTED_AT,
        jobId: null,
      },
    })

    const sections = screen.getByTestId('studio-support-rail-sections')
    const panels = Array.from(sections.querySelectorAll('[data-testid="studio-world-entry-panel"], [data-testid="studio-research-panel"]'))
      .map((node) => node.getAttribute('data-testid'))

    expect(panels).toEqual(['studio-world-entry-panel', 'studio-research-panel'])
    expect(screen.getByTestId('studio-world-entry-panel')).toHaveAttribute('data-prominence', 'elevated')
    expect(screen.getByTestId('studio-assistant-rail')).toHaveAttribute('data-world-entry-stage', 'attention')
    expect(screen.getByTestId('studio-world-entry-attention-banner')).toHaveAttribute('data-tone', 'running')
  })
})
