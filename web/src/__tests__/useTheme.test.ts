import { describe, it, expect, vi, beforeEach } from 'vitest'
import { renderHook, act } from '@testing-library/react'
import { useTheme } from '@/hooks/useTheme'

describe('useTheme', () => {
  beforeEach(() => {
    localStorage.clear()
    document.documentElement.classList.remove('light')
    document.documentElement.classList.remove('dark')
    vi.restoreAllMocks()
  })

  it('switches themes, syncs browser styling, and restores the saved choice', () => {
    const { result, unmount } = renderHook(() => useTheme())
    expect(result.current.theme).toBe('light')
    expect(document.documentElement.classList.contains('light')).toBe(true)
    expect(document.documentElement.style.colorScheme).toBe('light')

    act(() => result.current.toggleTheme())
    expect(result.current.theme).toBe('dark')
    expect(document.documentElement.classList.contains('light')).toBe(false)
    expect(document.documentElement.classList.contains('dark')).toBe(false)
    expect(document.documentElement.style.colorScheme).toBe('dark')
    expect(localStorage.getItem('novwr_theme')).toBe('dark')

    unmount()
    const restored = renderHook(() => useTheme())
    expect(restored.result.current.theme).toBe('dark')
    act(() => restored.result.current.toggleTheme())
    expect(restored.result.current.theme).toBe('light')
    expect(document.documentElement.classList.contains('light')).toBe(true)
    expect(document.documentElement.style.colorScheme).toBe('light')
    expect(localStorage.getItem('novwr_theme')).toBe('light')
  })

  it('falls back to light for invalid stored values', () => {
    localStorage.setItem('novwr_theme', 'banana')
    const { result } = renderHook(() => useTheme())
    expect(result.current.theme).toBe('light')
  })

  it('falls back to light when localStorage.getItem throws (SecurityError)', () => {
    vi.spyOn(Storage.prototype, 'getItem').mockImplementation(() => {
      throw new DOMException('denied', 'SecurityError')
    })
    const { result } = renderHook(() => useTheme())
    expect(result.current.theme).toBe('light')
  })

  it('does not throw when localStorage.setItem throws (QuotaExceededError)', () => {
    vi.spyOn(Storage.prototype, 'setItem').mockImplementation(() => {
      throw new DOMException('quota exceeded', 'QuotaExceededError')
    })
    const { result } = renderHook(() => useTheme())
    expect(() => {
      act(() => result.current.setTheme('dark'))
    }).not.toThrow()
    expect(result.current.theme).toBe('dark')
  })
})
