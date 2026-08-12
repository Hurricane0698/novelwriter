import { QueryClientProvider } from '@tanstack/react-query'
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, vi } from 'vitest'
import '@/lib/uiMessagePacks/novel'
import { ContinuationSetupStage } from '@/components/studio/stages/ContinuationSetupStage'
import { UiLocaleProvider } from '@/contexts/UiLocaleContext'
import { createTestQueryClient } from '@/__tests__/support/queryClient'

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

describe('ContinuationSetupStage ranged outlines', () => {
  it('selects, creates, and confirms deletion without flattening Markdown preview', async () => {
    const onSelectedOutlineIdsChange = vi.fn()
    const onCreateOutline = vi.fn()
    const onDeleteOutline = vi.fn().mockResolvedValue(undefined)
    const queryClient = createTestQueryClient()

    render(
      <QueryClientProvider client={queryClient}>
        <UiLocaleProvider>
          <ContinuationSetupStage
            novelId={7}
            contentFormat="markdown"
            chapterNum={10}
            chapterReference="第 10 章"
            instruction=""
            onInstructionChange={vi.fn()}
            selectedLength="3000"
            onSelectedLengthChange={vi.fn()}
            advancedOpen
            onAdvancedOpenChange={vi.fn()}
            contextChapters="5"
            onContextChaptersChange={vi.fn()}
            numVersions="1"
            onNumVersionsChange={vi.fn()}
            temperature="0.8"
            onTemperatureChange={vi.fn()}
            outlines={[{
              id: 9,
              novel_id: 7,
              start_chapter: 1,
              end_chapter: 10,
              title: '第1—10章剧情大纲',
              content: '摘要',
              model: 'test-model',
              created_at: '2026-08-12T00:00:00Z',
              updated_at: '2026-08-12T00:00:00Z',
            }]}
            outlinesLoading={false}
            outlineError={null}
            selectedOutlineIds={[]}
            onSelectedOutlineIdsChange={onSelectedOutlineIdsChange}
            outlineRange="1-10"
            onOutlineRangeChange={vi.fn()}
            outlineGenerating={false}
            outlineDeletingId={null}
            onCreateOutline={onCreateOutline}
            onDeleteOutline={onDeleteOutline}
            onGenerate={vi.fn()}
          />
        </UiLocaleProvider>
      </QueryClientProvider>,
    )

    expect(await screen.findByRole('heading', { level: 3, name: '场景' })).toBeInTheDocument()

    await userEvent.click(screen.getByRole('checkbox'))
    expect(onSelectedOutlineIdsChange).toHaveBeenCalledWith([9])

    await userEvent.click(screen.getByRole('button', { name: '生成大纲' }))
    expect(onCreateOutline).toHaveBeenCalledTimes(1)

    await userEvent.click(screen.getByRole('button', { name: '删除大纲“第1—10章剧情大纲”' }))
    expect(screen.getByTestId('confirm-dialog')).toHaveTextContent('删除后无法恢复')
    await userEvent.click(screen.getByTestId('confirm-ok'))
    expect(onDeleteOutline).toHaveBeenCalledWith(9)
  })
})
