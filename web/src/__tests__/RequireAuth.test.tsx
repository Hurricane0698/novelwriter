import { beforeEach, describe, expect, it, vi } from 'vitest'
import { render, screen } from '@testing-library/react'
import { MemoryRouter, Route, Routes, useLocation } from 'react-router-dom'

const authState = vi.hoisted(() => ({
  isLoggedIn: false,
  isLoading: false,
}))

vi.mock('@/contexts/AuthContext', () => ({
  useAuth: () => authState,
}))

import { RequireAuth } from '@/App'

function LocationProbe() {
  const location = useLocation()
  return <div data-testid="location-path">{location.pathname}</div>
}

function renderProtectedRoute() {
  return render(
    <MemoryRouter initialEntries={['/library']}>
      <Routes>
        <Route element={<RequireAuth />}>
          <Route path="/library" element={<div>local-library</div>} />
        </Route>
        <Route path="/login" element={<LocationProbe />} />
      </Routes>
    </MemoryRouter>,
  )
}

describe('RequireAuth', () => {
  beforeEach(() => {
    vi.unstubAllEnvs()
    authState.isLoggedIn = false
    authState.isLoading = false
  })

  it.each(['desktop', 'selfhost'] as const)('does not gate %s product routes behind login', (runtimeMode) => {
    vi.stubEnv('VITE_DEPLOY_MODE', runtimeMode)
    renderProtectedRoute()
    expect(screen.getByText('local-library')).toBeVisible()
    expect(screen.queryByTestId('location-path')).toBeNull()
  })

  it('keeps hosted routes protected', () => {
    vi.stubEnv('VITE_DEPLOY_MODE', 'hosted')
    renderProtectedRoute()
    expect(screen.getByTestId('location-path')).toHaveTextContent('/login')
  })
})
