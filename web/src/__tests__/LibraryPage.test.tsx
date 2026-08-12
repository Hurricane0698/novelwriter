import { createElement, type ReactNode } from 'react'
import { describe, it, expect, beforeEach, vi } from 'vitest'
import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter } from 'react-router-dom'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { UiLocaleProvider } from '@/contexts/UiLocaleContext'
import { LibraryPage } from '@/pages/LibraryPage'

const listNovels = vi.fn()
const uploadNovel = vi.fn()

vi.mock('@/services/api', () => ({
  api: {
    listNovels: (...args: unknown[]) => listNovels(...args),
    uploadNovel: (...args: unknown[]) => uploadNovel(...args),
    deleteNovel: vi.fn(),
  },
  ApiError: class ApiError extends Error {
    code?: string
    detail?: unknown
  },
}))

vi.mock('@/components/layout/PageShell', () => ({
  PageShell: ({ children }: { children: ReactNode }) => <div>{children}</div>,
}))

vi.mock('@/components/library/WorkCard', () => ({
  WorkCard: () => <div>work-card</div>,
}))

vi.mock('@/components/library/EmptyState', () => ({
  EmptyState: ({ onCreate }: { onCreate: () => void }) => (
    <button type="button" onClick={onCreate}>empty-create</button>
  ),
}))

vi.mock('@/lib/worldOnboardingStorage', () => ({
  clearWorldOnboardingDismissed: vi.fn(),
}))

function renderPage() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return render(
    createElement(
      MemoryRouter,
      null,
      createElement(
        UiLocaleProvider,
        null,
        createElement(QueryClientProvider, { client }, createElement(LibraryPage)),
      ),
    ),
  )
}

describe('LibraryPage', () => {
  beforeEach(() => {
    vi.restoreAllMocks()
    listNovels.mockResolvedValue([])
    uploadNovel.mockResolvedValue({ novel_id: 1, total_chapters: 2 })
    localStorage.clear()
    document.documentElement.lang = 'zh-CN'
  })

  it('shows create actions without a legal consent gate', async () => {
    renderPage()

    const createButton = await screen.findByTestId('library-create-novel')
    expect(createButton).not.toBeDisabled()
    expect(screen.queryByText('上传前先确认权利边界')).not.toBeInTheDocument()
  })

  it('uploads immediately without a library-side consent step', async () => {
    renderPage()

    const input = screen.getByTestId('library-file-input') as HTMLInputElement
    const file = new File(['hello'], 'test.txt', { type: 'text/plain' })
    await userEvent.upload(input, file)

    await waitFor(() => {
      expect(uploadNovel).toHaveBeenCalledWith(file, 'test', '', { sourceSurface: 'unknown' })
    })
  })

  it('accepts Markdown files and derives the title from the .md extension', async () => {
    renderPage()

    const input = screen.getByTestId('library-file-input') as HTMLInputElement
    expect(input.accept).toBe('.txt,.md')
    const file = new File(['## 第一章\n正文'], 'markdown-book.md', { type: 'text/markdown' })
    await userEvent.upload(input, file)

    await waitFor(() => {
      expect(uploadNovel).toHaveBeenCalledWith(file, 'markdown-book', '', { sourceSurface: 'unknown' })
    })
  })

  it('blocks further library actions while an upload is in flight', async () => {
    uploadNovel.mockImplementation(() => new Promise(() => {}))

    renderPage()

    const input = screen.getByTestId('library-file-input') as HTMLInputElement
    const file = new File(['hello'], 'queued.txt', { type: 'text/plain' })
    await userEvent.upload(input, file)

    expect(await screen.findByTestId('library-upload-overlay')).toBeInTheDocument()
    expect(screen.getByTestId('library-create-novel')).toBeDisabled()
  })

  it('renders core library copy in English when the UI locale is en', async () => {
    localStorage.setItem('novwr_ui_locale', 'en')
    document.documentElement.lang = 'en'

    renderPage()

    expect(await screen.findByRole('heading', { name: 'Library' })).toBeVisible()
    expect(screen.getByRole('button', { name: /New novel/i })).toBeVisible()
  })

  it('renders the seeded demo novel as a normal work card without a guide entry', async () => {
    listNovels.mockResolvedValue([
      {
        id: 7,
        title: '西游记',
        author: '吴承恩',
        language: 'zh',
        total_chapters: 27,
        is_seeded_demo: true,
        created_at: '2026-03-01T00:00:00Z',
        updated_at: '2026-03-01T00:00:00Z',
        window_index: {
          status: 'fresh',
          revision: 1,
          built_revision: 1,
          error: null,
          readiness: 'ready',
          capabilities: {
            chapters_available: true,
            whole_book_index_available: true,
            bootstrap_available: true,
            recent_fallback_only: false,
          },
          job: null,
        },
      },
    ])

    renderPage()

    expect(await screen.findByText('work-card')).toBeInTheDocument()
    expect(screen.queryByTestId('library-demo-entry')).toBeNull()
  })
})
