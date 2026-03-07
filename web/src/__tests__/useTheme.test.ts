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

  it('defaults to dark when no preference saved', () => {
    const { result } = renderHook(() => useTheme())
    expect(result.current.theme).toBe('dark')
  })

  it('reads from localStorage', () => {
    localStorage.setItem('novwr_theme', 'light')
    const { result } = renderHook(() => useTheme())
    expect(result.current.theme).toBe('light')
  })

  it('adds .light class only when light mode is active', () => {
    localStorage.setItem('novwr_theme', 'light')
    renderHook(() => useTheme())
    expect(document.documentElement.classList.contains('light')).toBe(true)
  })

  it('does not add any class for dark mode (dark is default)', () => {
    const { result } = renderHook(() => useTheme())
    expect(result.current.theme).toBe('dark')
    expect(document.documentElement.classList.contains('light')).toBe(false)
    expect(document.documentElement.classList.contains('dark')).toBe(false)
  })

  it('toggleTheme switches dark → light → dark', () => {
    const { result } = renderHook(() => useTheme())
    expect(result.current.theme).toBe('dark')

    act(() => result.current.toggleTheme())
    expect(result.current.theme).toBe('light')
    expect(document.documentElement.classList.contains('light')).toBe(true)

    act(() => result.current.toggleTheme())
    expect(result.current.theme).toBe('dark')
    expect(document.documentElement.classList.contains('light')).toBe(false)
  })

  it('persists theme to localStorage', () => {
    const { result } = renderHook(() => useTheme())
    act(() => result.current.setTheme('light'))
    expect(localStorage.getItem('novwr_theme')).toBe('light')
  })

  it('falls back to dark for invalid stored values', () => {
    localStorage.setItem('novwr_theme', 'banana')
    const { result } = renderHook(() => useTheme())
    expect(result.current.theme).toBe('dark')
  })

  it('falls back to dark when localStorage.getItem throws (SecurityError)', () => {
    vi.spyOn(Storage.prototype, 'getItem').mockImplementation(() => {
      throw new DOMException('denied', 'SecurityError')
    })
    const { result } = renderHook(() => useTheme())
    expect(result.current.theme).toBe('dark')
  })

  it('does not throw when localStorage.setItem throws (QuotaExceededError)', () => {
    vi.spyOn(Storage.prototype, 'setItem').mockImplementation(() => {
      throw new DOMException('quota exceeded', 'QuotaExceededError')
    })
    const { result } = renderHook(() => useTheme())
    expect(() => {
      act(() => result.current.setTheme('light'))
    }).not.toThrow()
    expect(result.current.theme).toBe('light')
  })

  it('sets color-scheme on documentElement', () => {
    const { result } = renderHook(() => useTheme())
    expect(document.documentElement.style.colorScheme).toBe('dark')
    act(() => result.current.setTheme('light'))
    expect(document.documentElement.style.colorScheme).toBe('light')
  })
})
