import { beforeEach, describe, expect, it, vi } from 'vitest'
import { render, screen, waitFor } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'

import { AnimatedBackground } from '@/components/layout/AnimatedBackground'
import { PerformanceModeProvider, usePerformanceMode } from '@/contexts/PerformanceModeContext'

function ModeProbe() {
  const { mode, isLite, routeSurface, showAmbientBackground } = usePerformanceMode()
  return (
    <div>
      <span data-testid="mode">{mode}</span>
      <span data-testid="is-lite">{String(isLite)}</span>
      <span data-testid="route-surface">{routeSurface}</span>
      <span data-testid="ambient-bg">{String(showAmbientBackground)}</span>
    </div>
  )
}

function renderHarness(initialEntry: string) {
  return render(
    <MemoryRouter initialEntries={[initialEntry]}>
      <PerformanceModeProvider>
        <ModeProbe />
        <AnimatedBackground />
      </PerformanceModeProvider>
    </MemoryRouter>,
  )
}

describe('PerformanceModeProvider', () => {
  beforeEach(() => {
    localStorage.clear()
    delete document.documentElement.dataset.perfMode
    delete document.documentElement.dataset.routeSurface
    vi.restoreAllMocks()
  })

  it('keeps the animated background off on the marketing landing page', () => {
    renderHarness('/')
    expect(screen.getByTestId('mode')).toHaveTextContent('default')
    expect(screen.getByTestId('is-lite')).toHaveTextContent('false')
    expect(screen.getByTestId('route-surface')).toHaveTextContent('marketing')
    expect(screen.getByTestId('ambient-bg')).toHaveTextContent('false')
    expect(screen.queryByTestId('animated-background')).not.toBeInTheDocument()
    expect(document.documentElement.dataset.perfMode).toBeUndefined()
    expect(document.documentElement.dataset.routeSurface).toBe('marketing')
  })

  it('keeps the animated background on non-landing marketing routes by default', () => {
    renderHarness('/login')
    expect(screen.getByTestId('mode')).toHaveTextContent('default')
    expect(screen.getByTestId('is-lite')).toHaveTextContent('false')
    expect(screen.getByTestId('route-surface')).toHaveTextContent('marketing')
    expect(screen.getByTestId('ambient-bg')).toHaveTextContent('true')
    expect(screen.getByTestId('animated-background')).toBeInTheDocument()
    expect(document.documentElement.dataset.perfMode).toBeUndefined()
    expect(document.documentElement.dataset.routeSurface).toBe('marketing')
  })

  it('disables the animated background on workspace routes by default', () => {
    renderHarness('/library')

    expect(screen.getByTestId('mode')).toHaveTextContent('default')
    expect(screen.getByTestId('is-lite')).toHaveTextContent('false')
    expect(screen.getByTestId('route-surface')).toHaveTextContent('workspace')
    expect(screen.getByTestId('ambient-bg')).toHaveTextContent('false')
    expect(screen.queryByTestId('animated-background')).not.toBeInTheDocument()
    expect(document.documentElement.dataset.routeSurface).toBe('workspace')
  })

  it('ignores saved lite mode on the marketing landing page', async () => {
    localStorage.setItem('novwr_perf_mode', 'lite')

    renderHarness('/')

    await waitFor(() => {
      expect(screen.getByTestId('mode')).toHaveTextContent('default')
    })
    expect(screen.getByTestId('is-lite')).toHaveTextContent('false')
    expect(screen.getByTestId('route-surface')).toHaveTextContent('marketing')
    // Landing uses the lattice stage — ambient blobs stay off even with stored lite.
    expect(screen.getByTestId('ambient-bg')).toHaveTextContent('false')
    expect(screen.queryByTestId('animated-background')).not.toBeInTheDocument()
    expect(document.documentElement.dataset.perfMode).toBeUndefined()
  })

  it('still applies the saved lite mode on workspace routes', async () => {
    localStorage.setItem('novwr_perf_mode', 'lite')

    renderHarness('/library')

    await waitFor(() => {
      expect(screen.getByTestId('mode')).toHaveTextContent('lite')
    })
    expect(screen.getByTestId('is-lite')).toHaveTextContent('true')
    expect(screen.getByTestId('route-surface')).toHaveTextContent('workspace')
    expect(screen.getByTestId('ambient-bg')).toHaveTextContent('false')
    expect(screen.queryByTestId('animated-background')).not.toBeInTheDocument()
    expect(document.documentElement.dataset.perfMode).toBe('lite')
  })

  it('accepts ?perf=lite and persists it for later navigation', async () => {
    renderHarness('/novel/7?perf=lite')

    await waitFor(() => {
      expect(screen.getByTestId('mode')).toHaveTextContent('lite')
    })
    expect(screen.getByTestId('is-lite')).toHaveTextContent('true')
    expect(screen.getByTestId('route-surface')).toHaveTextContent('workspace')
    expect(screen.getByTestId('ambient-bg')).toHaveTextContent('false')
    expect(screen.queryByTestId('animated-background')).not.toBeInTheDocument()
    expect(localStorage.getItem('novwr_perf_mode')).toBe('lite')
    expect(document.documentElement.dataset.perfMode).toBe('lite')
    expect(document.documentElement.dataset.routeSurface).toBe('workspace')
  })

  it('accepts ?perf=default and clears a previously saved lite mode', async () => {
    localStorage.setItem('novwr_perf_mode', 'lite')

    renderHarness('/login?perf=default')

    await waitFor(() => {
      expect(screen.getByTestId('mode')).toHaveTextContent('default')
    })
    expect(screen.getByTestId('is-lite')).toHaveTextContent('false')
    expect(screen.getByTestId('route-surface')).toHaveTextContent('marketing')
    expect(screen.getByTestId('ambient-bg')).toHaveTextContent('true')
    expect(screen.getByTestId('animated-background')).toBeInTheDocument()
    expect(localStorage.getItem('novwr_perf_mode')).toBeNull()
    expect(document.documentElement.dataset.perfMode).toBeUndefined()
    expect(document.documentElement.dataset.routeSurface).toBe('marketing')
  })
})
