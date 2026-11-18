import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import type { ReactNode } from 'react'
import { act, render, screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { InjectionSection } from '@/components/home/InjectionSection'
import { readLandingPalette } from '@/components/home/shader/readLandingPalette'
import { SurfaceTabs } from '@/components/home/SurfaceTabs'
import { MemoryRouter } from 'react-router-dom'
import { QueryClientProvider } from '@tanstack/react-query'
import '@/lib/uiMessagePacks/home'
import { UiLocaleProvider } from '@/contexts/UiLocaleContext'
import { PerformanceModeProvider } from '@/contexts/PerformanceModeContext'
import { HeroSection } from '@/components/home/HeroSection'
import { HomeDeferredSections } from '@/components/home/HomeDeferredSections'
import { Navbar } from '@/components/layout/Navbar'
import Settings from '@/pages/Settings'
import { createTestQueryClient } from '@/__tests__/support/queryClient'

function setEnglishLocale() {
  localStorage.setItem('novwr_ui_locale', 'en')
  document.documentElement.lang = 'en'
}

function renderWithLocale(element: ReactNode) {
  const queryClient = createTestQueryClient()
  return render(
    <QueryClientProvider client={queryClient}>
      <UiLocaleProvider>
        <MemoryRouter>
          <PerformanceModeProvider>
            {element}
          </PerformanceModeProvider>
        </MemoryRouter>
      </UiLocaleProvider>
    </QueryClientProvider>,
  )
}

describe('public locale surfaces', () => {
  beforeEach(() => {
    vi.restoreAllMocks()
    vi.unstubAllEnvs()
    vi.stubEnv('VITE_DEPLOY_MODE', 'selfhost')
    localStorage.clear()
    document.documentElement.lang = 'zh-CN'
  })

  afterEach(() => {
    vi.unstubAllEnvs()
  })

  it('renders the marketing home copy in English', async () => {
    setEnglishLocale()

    renderWithLocale(
      <>
        <HeroSection />
        <HomeDeferredSections />
      </>,
    )

    expect(screen.getByRole('heading', { name: /Understand the world first\.\s*Write better stories\./ })).toBeInTheDocument()
    expect(await screen.findByRole('heading', { name: 'Bring your world into this chapter' })).toBeInTheDocument()
    expect(await screen.findByRole('heading', { name: 'One novel, three perspectives' })).toBeInTheDocument()
    expect(await screen.findByRole('heading', { name: 'From manuscript to the next chapter' })).toBeInTheDocument()
    expect(await screen.findByRole('heading', { name: 'Your world has another chapter' })).toBeInTheDocument()
    expect(screen.queryByText('三个界面')).not.toBeInTheDocument()
    expect(screen.queryByText('设计细节')).not.toBeInTheDocument()
  })

  it('exposes focusable lattice entity nodes with surface and truth layers', async () => {
    setEnglishLocale()

    renderWithLocale(<HeroSection />)

    const node = screen.getByRole('button', { name: /唐僧/ })
    act(() => node.focus())
    expect(node).toHaveFocus()
    expect(await screen.findByText('Surface')).toBeInTheDocument()
    expect(await screen.findByText('Truth')).toBeInTheDocument()
    expect(screen.getByText(/金蝉子/)).toBeInTheDocument()
  })

  it('reads percentage-based theme tokens instead of falling back to white', () => {
    const root = document.documentElement
    root.style.setProperty('--lp-paper', '0 0% 0%')
    root.style.setProperty('--lp-thread', '235 78% 74%')
    try {
      const dark = readLandingPalette()
      expect(dark.paper).toEqual([0, 0, 0])
      expect(dark.thread[0]).toBeCloseTo(0.5372)
      root.style.setProperty('--lp-paper', '0 0% 100%')
      expect(readLandingPalette().paper).toEqual([1, 1, 1])
    } finally {
      root.style.removeProperty('--lp-paper')
      root.style.removeProperty('--lp-thread')
    }
  })

  it('keeps a clicked lattice node open and dismisses it with Escape', async () => {
    const user = userEvent.setup()
    setEnglishLocale()
    renderWithLocale(<HeroSection />)
    await user.click(screen.getByRole('button', { name: '唐僧' }))
    expect(screen.getByRole('button', { name: '唐僧' })).toHaveAttribute('aria-pressed', 'true')
    expect(screen.getByText(/金蝉子/)).toBeVisible()
    await user.keyboard('{Escape}')
    expect(screen.queryByText(/金蝉子/)).not.toBeInTheDocument()
  })

  it('selects excerpt settings and switches their visible layer', async () => {
    const user = userEvent.setup()
    setEnglishLocale()
    renderWithLocale(<InjectionSection />)
    const article = screen.getByRole('article')
    await user.click(within(article).getByRole('button', { name: '唐僧' }))
    expect(screen.getByRole('heading', { name: '唐僧' })).toBeVisible()
    await user.click(screen.getByRole('button', { name: 'Truth' }))
    expect(screen.getByText(/金蝉子/)).toBeVisible()
    await user.click(within(article).getByRole('button', { name: '念咒' }))
    expect(screen.getByRole('heading', { name: '紧箍咒' })).toBeVisible()
  })

  it('switches the product screenshot and caption with the keyboard', async () => {
    const user = userEvent.setup()
    setEnglishLocale()
    renderWithLocale(<SurfaceTabs />)
    screen.getByRole('tab', { name: 'Studio' }).focus()
    await user.keyboard('{ArrowRight}')
    expect(screen.getByRole('tab', { name: 'Atlas' })).toHaveFocus()
    expect(screen.getByRole('tab', { name: 'Atlas' })).toHaveAttribute('aria-selected', 'true')
    expect(screen.getByRole('img', { name: 'NovWr Atlas workspace' })).toBeVisible()
    expect(screen.queryByRole('img', { name: 'NovWr Studio workspace' })).not.toBeInTheDocument()
    await user.keyboard('{End}')
    expect(screen.getByRole('tab', { name: 'Copilot' })).toHaveFocus()
  })

  it.each(['desktop', 'selfhost'] as const)('routes the local %s landing directly into the product', (runtimeMode) => {
    vi.stubEnv('VITE_DEPLOY_MODE', runtimeMode)
    setEnglishLocale()

    renderWithLocale(
      <>
        <Navbar />
        <HeroSection />
      </>,
    )

    expect(screen.getByTestId('home-start-writing')).toHaveAttribute('href', '/library')
    expect(screen.queryByRole('link', { name: 'Log in' })).toBeNull()
    expect(screen.getByRole('link', { name: 'Library' })).toHaveAttribute('href', '/library')
  })

  it('renders the settings surface in English', () => {
    setEnglishLocale()

    renderWithLocale(<Settings />)

    expect(screen.getByRole('heading', { name: 'Settings' })).toBeVisible()
    expect(screen.getByText('Interface language')).toBeVisible()
    expect(screen.getByRole('button', { name: 'Test connection' })).toBeVisible()
  })

})
