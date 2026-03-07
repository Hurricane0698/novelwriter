import { describe, it, expect, vi, beforeEach } from 'vitest'
import { renderHook, act, waitFor } from '@testing-library/react'
import React from 'react'
import { AuthProvider, useAuth } from '@/contexts/AuthContext'
import { api } from '@/services/api'
import { createQueryClientWrapper } from '@/__tests__/helpers'

function wrapper({ children }: { children: React.ReactNode }) {
  const QueryClientWrapper = createQueryClientWrapper()
  return React.createElement(QueryClientWrapper, null, React.createElement(AuthProvider, null, children))
}

describe('useAuth', () => {
  beforeEach(() => {
    vi.restoreAllMocks()
  })

  it('throws when used outside AuthProvider', () => {
    expect(() => renderHook(() => useAuth())).toThrow('useAuth must be used within an AuthProvider')
  })

  it('starts logged out when /api/auth/me returns 401', async () => {
    vi.spyOn(globalThis, 'fetch').mockResolvedValue(new Response('Not authenticated', { status: 401 }))

    const { result } = renderHook(() => useAuth(), { wrapper })
    await waitFor(() => expect(result.current.isLoading).toBe(false))

    expect(result.current.isLoggedIn).toBe(false)
    expect(result.current.user).toBeNull()
  })

  it('sets user when /api/auth/me returns 200', async () => {
    const me = { id: 1, username: 'default', role: 'admin', is_active: true }
    vi.spyOn(globalThis, 'fetch').mockResolvedValue(
      new Response(JSON.stringify(me), { status: 200, headers: { 'content-type': 'application/json' } }),
    )

    const { result } = renderHook(() => useAuth(), { wrapper })
    await waitFor(() => expect(result.current.isLoading).toBe(false))

    expect(result.current.isLoggedIn).toBe(true)
    expect(result.current.user?.username).toBe('default')
  })

  it('probe sends cookies with /api/auth/me request', async () => {
    const me = { id: 1, username: 'u', role: 'user', is_active: true }
    const fetchMock = vi.spyOn(globalThis, 'fetch').mockResolvedValue(
      new Response(JSON.stringify(me), { status: 200, headers: { 'content-type': 'application/json' } }),
    )

    const { result } = renderHook(() => useAuth(), { wrapper })
    await waitFor(() => expect(result.current.isLoading).toBe(false))

    expect(fetchMock).toHaveBeenCalled()
    const init = fetchMock.mock.calls[0]?.[1] as RequestInit | undefined
    expect(init?.credentials).toBe('include')
  })

  it('login refreshes user via probe()', async () => {
    const me = { id: 2, username: 'alice', role: 'user', is_active: true }
    vi.spyOn(api, 'login').mockResolvedValue({ access_token: 'jwt-xyz', token_type: 'bearer' })
    vi.spyOn(globalThis, 'fetch')
      .mockResolvedValueOnce(new Response('Not authenticated', { status: 401 })) // initial probe
      .mockResolvedValueOnce(
        new Response(JSON.stringify(me), { status: 200, headers: { 'content-type': 'application/json' } }),
      ) // probe after login

    const { result } = renderHook(() => useAuth(), { wrapper })
    await waitFor(() => expect(result.current.isLoading).toBe(false))

    await act(async () => {
      await result.current.login('alice', 'pw')
    })

    await waitFor(() => expect(result.current.isLoggedIn).toBe(true))
    expect(result.current.user?.username).toBe('alice')
  })

  it('logout clears user and calls logout API', async () => {
    const me = { id: 1, username: 'u', role: 'user', is_active: true }
    vi.spyOn(api, 'logout').mockResolvedValue(undefined)
    vi.spyOn(globalThis, 'fetch').mockResolvedValue(
      new Response(JSON.stringify(me), { status: 200, headers: { 'content-type': 'application/json' } }),
    )

    const { result } = renderHook(() => useAuth(), { wrapper })
    await waitFor(() => expect(result.current.isLoading).toBe(false))
    expect(result.current.isLoggedIn).toBe(true)

    await act(async () => {
      await result.current.logout()
    })

    expect(result.current.isLoggedIn).toBe(false)
    expect(result.current.user).toBeNull()
    expect(api.logout).toHaveBeenCalled()
  })
})
