import { useState } from 'react'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { act, render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter } from 'react-router-dom'
import { UiLocaleProvider } from '@/contexts/UiLocaleContext'
import { WorldGenerationDialog } from '@/components/world-model/shared/WorldGenerationDialog'
import { ApiError } from '@/services/api'
import type { WorldpackImportResponse } from '@/types/api'

const mockUseGenerateWorld = vi.fn()
const mockUseImportWorldpack = vi.fn()
const navigateMock = vi.fn()
const trackHostedAnalyticsEventMock = vi.fn().mockResolvedValue(true)

vi.mock('@/hooks/world/useWorldGeneration', () => ({
  useGenerateWorld: (...args: unknown[]) => mockUseGenerateWorld(...args),
}))

vi.mock('@/hooks/world/useWorldpack', () => ({
  useImportWorldpack: (...args: unknown[]) => mockUseImportWorldpack(...args),
}))

vi.mock('@/lib/hostedAnalytics', () => ({
  trackHostedAnalyticsEvent: (...args: unknown[]) => trackHostedAnalyticsEventMock(...args),
}))

vi.mock('react-router-dom', async () => {
  const actual = await vi.importActual<typeof import('react-router-dom')>('react-router-dom')
  return {
    ...actual,
    useNavigate: () => navigateMock,
  }
})

function renderDialog(
  props?: Partial<Parameters<typeof WorldGenerationDialog>[0]>,
) {
  return render(
    <MemoryRouter>
      <UiLocaleProvider>
        <WorldGenerationDialog novelId={7} open onOpenChange={vi.fn()} {...props} />
      </UiLocaleProvider>
    </MemoryRouter>,
  )
}

describe('WorldGenerationDialog', () => {
  beforeEach(() => {
    vi.restoreAllMocks()
    localStorage.clear()
    document.documentElement.lang = 'zh-CN'
    mockUseGenerateWorld.mockReturnValue({ mutate: vi.fn(), isPending: false })
    mockUseImportWorldpack.mockReturnValue({ mutate: vi.fn(), isPending: false })
    navigateMock.mockReset()
    trackHostedAnalyticsEventMock.mockReset()
    trackHostedAnalyticsEventMock.mockResolvedValue(true)
  })

  it('removes closed controls, restores focus, and rejects a previous dialog session completion', async () => {
    let complete!: (response: unknown) => void
    const onGenerateSuccess = vi.fn()
    mockUseGenerateWorld.mockReturnValue({
      mutate: vi.fn((_data, options) => { complete = options.onSuccess }), isPending: false,
    })
    function Host() {
      const [open, setOpen] = useState(false)
      return <>
        <button onClick={() => setOpen(true)}>open-generator</button>
        <input aria-label="chapter draft" />
        <WorldGenerationDialog novelId={7} open={open} onOpenChange={setOpen} onGenerateSuccess={onGenerateSuccess} />
      </>
    }
    render(<MemoryRouter><UiLocaleProvider><Host /></UiLocaleProvider></MemoryRouter>)
    expect(screen.queryByTestId('world-gen-text')).not.toBeInTheDocument()
    const user = userEvent.setup()
    const trigger = screen.getByRole('button', { name: 'open-generator' })
    await user.click(trigger)
    await user.type(screen.getByTestId('world-gen-text'), 'Enough setting text to generate a world.')
    await user.click(screen.getByTestId('world-gen-submit'))
    await user.click(screen.getByRole('button', { name: '取消' }))
    expect(trigger).toHaveFocus()
    expect(screen.queryByTestId('world-gen-text')).not.toBeInTheDocument()
    await user.tab()
    expect(screen.getByLabelText('chapter draft')).toHaveFocus()
    await user.type(screen.getByLabelText('chapter draft'), 'unsaved chapter')
    await user.click(trigger)
    act(() => complete({ entities_created: 1, relationships_created: 0, systems_created: 0 }))
    expect(navigateMock).not.toHaveBeenCalled()
    expect(onGenerateSuccess).not.toHaveBeenCalled()
    expect(screen.getByLabelText('chapter draft')).toHaveValue('unsaved chapter')
    expect(screen.getByTestId('world-gen-text')).toBeInTheDocument()
  })

  it('renders LLM failures in English when the UI locale is en', async () => {
    localStorage.setItem('novwr_ui_locale', 'en')
    document.documentElement.lang = 'en'
    const mutate = vi.fn((_payload, options) => {
      options?.onError?.(
        new ApiError(503, 'HTTP 503', {
          code: 'world_generate_llm_unavailable',
          detail: { code: 'world_generate_llm_unavailable' },
        }),
      )
    })
    mockUseGenerateWorld.mockReturnValue({ mutate, isPending: false })

    renderDialog()

    await userEvent.type(screen.getByTestId('world-gen-text'), 'Enough setting text to trigger world generation.')
    await userEvent.click(screen.getByTestId('world-gen-submit'))

    expect(await screen.findByTestId('world-gen-error')).toHaveTextContent(
      'The current model is unavailable. Check that Base URL, API Key, and Model match and that the endpoint supports JSON mode.',
    )
  })

  it('uses worldpack-specific failure copy for import request errors', async () => {
    localStorage.setItem('novwr_ui_locale', 'en')
    document.documentElement.lang = 'en'
    const mutate = vi.fn((_payload, options) => {
      options?.onError?.(new Error('import failed'))
    })
    mockUseImportWorldpack.mockReturnValue({ mutate, isPending: false })

    const { container } = renderDialog()
    const fileInput = container.querySelector('input[type="file"]') as HTMLInputElement | null
    expect(fileInput).not.toBeNull()

    const file = new File(
      [JSON.stringify({ schema_version: 'worldpack.v1', pack_name: 'Atlas seed' })],
      'worldpack.json',
      { type: 'application/json' },
    )
    Object.defineProperty(file, 'text', {
      configurable: true,
      value: vi.fn().mockResolvedValue(JSON.stringify({ schema_version: 'worldpack.v1', pack_name: 'Atlas seed' })),
    })

    await userEvent.upload(fileInput!, file)

    await waitFor(() => {
      expect(screen.getByText('Worldpack import failed. Please try again.')).toBeTruthy()
    })
  })

  it('tracks setting-generation submit events before mutating', async () => {
    const mutate = vi.fn()
    mockUseGenerateWorld.mockReturnValue({ mutate, isPending: false })

    renderDialog()

    await userEvent.type(screen.getByTestId('world-gen-text'), 'Enough setting text to trigger world generation.')
    await userEvent.click(screen.getByTestId('world-gen-submit'))

    expect(trackHostedAnalyticsEventMock).toHaveBeenCalledWith('world_generate_submit', expect.objectContaining({
      novelId: 7,
      meta: expect.objectContaining({
        source_surface: 'unknown',
      }),
    }))
    expect(mutate).toHaveBeenCalled()
  })

  it('lets import success stay in-place when the caller opts out of hard navigation', async () => {
    const onImportSuccess = vi.fn()
    const response: WorldpackImportResponse = {
      pack_id: 'pack-1',
      counts: {
        entities_created: 2,
        entities_updated: 0,
        entities_deleted: 0,
        attributes_created: 0,
        attributes_updated: 0,
        attributes_deleted: 0,
        relationships_created: 1,
        relationships_updated: 0,
        relationships_deleted: 0,
        systems_created: 1,
        systems_updated: 0,
        systems_deleted: 0,
      },
      warnings: [],
    }
    const mutate = vi.fn((_payload, options) => {
      options?.onSuccess?.(response)
    })
    mockUseImportWorldpack.mockReturnValue({ mutate, isPending: false })

    const { container } = renderDialog({
      onImportSuccess,
      navigateOnImportSuccess: false,
    })
    const fileInput = container.querySelector('input[type="file"]') as HTMLInputElement | null
    expect(fileInput).not.toBeNull()

    const file = new File(
      [JSON.stringify({ schema_version: 'worldpack.v1', pack_name: 'Atlas seed' })],
      'worldpack.json',
      { type: 'application/json' },
    )
    Object.defineProperty(file, 'text', {
      configurable: true,
      value: vi.fn().mockResolvedValue(JSON.stringify({ schema_version: 'worldpack.v1', pack_name: 'Atlas seed' })),
    })

    await userEvent.upload(fileInput!, file)

    await waitFor(() => {
      expect(onImportSuccess).toHaveBeenCalledWith(response)
    })
    expect(navigateMock).not.toHaveBeenCalled()
  })
})
