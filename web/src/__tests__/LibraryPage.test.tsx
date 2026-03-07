import { createElement, type ReactNode } from 'react'
import { describe, it, expect, beforeEach, vi } from 'vitest'
import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter } from 'react-router-dom'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { LibraryPage } from '@/pages/LibraryPage'
import { getUploadConsentKey, UPLOAD_CONSENT_VERSION } from '@/lib/uploadConsent'

const listNovels = vi.fn()
const uploadNovel = vi.fn()

vi.mock('@/services/api', () => ({
  api: {
    listNovels: (...args: unknown[]) => listNovels(...args),
    uploadNovel: (...args: unknown[]) => uploadNovel(...args),
    deleteNovel: vi.fn(),
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

vi.mock('@/contexts/AuthContext', () => ({
  useAuth: () => ({ user: { id: 7 } }),
}))

function renderPage() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return render(
    createElement(
      MemoryRouter,
      null,
      createElement(QueryClientProvider, { client }, createElement(LibraryPage)),
    ),
  )
}

describe('LibraryPage', () => {
  beforeEach(() => {
    vi.restoreAllMocks()
    localStorage.clear()
    listNovels.mockResolvedValue([])
    uploadNovel.mockResolvedValue({ novel_id: 1, total_chapters: 2 })
  })

  it('keeps upload disabled until consent is checked', async () => {
    renderPage()

    const createButton = await screen.findByTestId('library-create-novel')
    expect(createButton).toBeDisabled()

    const checkbox = screen.getByRole('checkbox')
    await userEvent.click(checkbox)

    expect(createButton).not.toBeDisabled()
    expect(localStorage.getItem(getUploadConsentKey(7))).toBe('1')
  })

  it('restores upload consent from localStorage', async () => {
    localStorage.setItem(getUploadConsentKey(7), '1')

    renderPage()

    await waitFor(() => {
      expect(screen.getByTestId('library-create-novel')).not.toBeDisabled()
    })
  })

  it('submits consent version with upload', async () => {
    localStorage.setItem(getUploadConsentKey(7), '1')
    renderPage()

    const input = screen.getByTestId('library-file-input') as HTMLInputElement
    const file = new File(['hello'], 'test.txt', { type: 'text/plain' })
    await userEvent.upload(input, file)

    await waitFor(() => {
      expect(uploadNovel).toHaveBeenCalledWith(file, 'test', '', UPLOAD_CONSENT_VERSION)
    })
  })
})
