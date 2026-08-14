import { QueryClientProvider } from '@tanstack/react-query'
import type { ComponentProps } from 'react'
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, vi } from 'vitest'
import '@/lib/uiMessagePacks/novel'
import { ContinuationSetupStage } from '@/components/studio/stages/ContinuationSetupStage'
import { UiLocaleProvider } from '@/contexts/UiLocaleContext'
import { createTestQueryClient } from '@/__tests__/support/queryClient'
import type { NovelContextSummary } from '@/types/api'

vi.mock('@/services/api', () => ({
  api: {
    getChapter: vi.fn().mockResolvedValue({
      id: 10,
      novel_id: 7,
      chapter_number: 10,
      title: '门后',
      source_chapter_label: null,
      source_chapter_number: null,
      source_volume_title: '第一卷',
      content: '### 场景\n\n门后传来回声。',
      created_at: '2026-08-12T00:00:00Z',
      updated_at: null,
    }),
  },
}))

const confirmedSummary: NovelContextSummary = {
  id: 9,
  novel_id: 7,
  start_chapter: 1,
  end_chapter: 10,
  title: '第1—10章远期剧情回顾',
  content: '主角找到旧钥匙。',
  model: 'test-model',
  review_status: 'confirmed',
  is_stale: false,
  created_at: '2026-08-12T00:00:00Z',
  updated_at: '2026-08-12T00:00:00Z',
}

function renderStage(overrides: Partial<ComponentProps<typeof ContinuationSetupStage>> = {}) {
  const props: ComponentProps<typeof ContinuationSetupStage> = {
    novelId: 7,
    contentFormat: 'markdown',
    chapterNum: 10,
    chapterReference: '第 10 章',
    instruction: '',
    onInstructionChange: vi.fn(),
    selectedLength: '3000',
    onSelectedLengthChange: vi.fn(),
    advancedOpen: true,
    onAdvancedOpenChange: vi.fn(),
    contextChapters: '5',
    onContextChaptersChange: vi.fn(),
    numVersions: '1',
    onNumVersionsChange: vi.fn(),
    temperature: '0.8',
    onTemperatureChange: vi.fn(),
    contextSummaries: [confirmedSummary],
    contextSummariesLoading: false,
    contextSummaryError: null,
    selectedContextSummaryIds: [],
    onSelectedContextSummaryIdsChange: vi.fn(),
    contextSummaryRange: '1-10',
    onContextSummaryRangeChange: vi.fn(),
    contextSummaryGenerating: false,
    contextSummaryDeletingId: null,
    contextSummarySaving: false,
    contextSummaryRegenerating: false,
    reviewContextSummary: null,
    onReviewContextSummaryChange: vi.fn(),
    onCreateContextSummary: vi.fn(),
    onSaveContextSummary: vi.fn().mockResolvedValue(confirmedSummary),
    onRegenerateContextSummary: vi.fn().mockResolvedValue({
      ...confirmedSummary,
      review_status: 'draft',
    }),
    onDeleteContextSummary: vi.fn().mockResolvedValue(undefined),
    onGenerate: vi.fn(),
    ...overrides,
  }
  const queryClient = createTestQueryClient()
  render(
    <QueryClientProvider client={queryClient}>
      <UiLocaleProvider>
        <ContinuationSetupStage {...props} />
      </UiLocaleProvider>
    </QueryClientProvider>,
  )
  return props
}

describe('ContinuationSetupStage distant chapter recaps', () => {
  it('selects only ready recaps, creates ranges, and confirms deletion', async () => {
    const props = renderStage()
    expect(await screen.findByRole('heading', { level: 3, name: '场景' })).toBeInTheDocument()

    await userEvent.click(screen.getByRole('checkbox'))
    expect(props.onSelectedContextSummaryIdsChange).toHaveBeenCalledWith([9])

    await userEvent.click(screen.getByRole('button', { name: '生成回顾' }))
    expect(props.onCreateContextSummary).toHaveBeenCalledTimes(1)

    await userEvent.click(screen.getByRole('button', { name: '删除回顾“第1—10章远期剧情回顾”' }))
    expect(screen.getByTestId('confirm-dialog')).toHaveTextContent('删除后无法恢复')
    await userEvent.click(screen.getByTestId('confirm-ok'))
    expect(props.onDeleteContextSummary).toHaveBeenCalledWith(9)
  })

  it('previews, edits, and explicitly confirms a generated recap', async () => {
    const draft = { ...confirmedSummary, review_status: 'draft' as const }
    const props = renderStage({ reviewContextSummary: draft })
    const editor = screen.getByTestId('context-summary-content')
    expect(editor).toHaveValue('主角找到旧钥匙。')
    await userEvent.clear(editor)
    await userEvent.type(editor, '作者核对后的剧情回顾。')
    await userEvent.click(screen.getByRole('button', { name: '确认并用于本次续写' }))
    expect(props.onSaveContextSummary).toHaveBeenCalledWith(
      9,
      '作者核对后的剧情回顾。',
      'confirmed',
    )
  })

  it('disables stale recaps and requires regeneration', () => {
    const stale = { ...confirmedSummary, is_stale: true }
    renderStage({ contextSummaries: [stale], reviewContextSummary: stale })
    expect(screen.getByRole('checkbox')).toBeDisabled()
    expect(screen.getByRole('button', { name: '确认并用于本次续写' })).toBeDisabled()
    expect(screen.getByText(/源章节已经变化/)).toBeInTheDocument()
  })
})
