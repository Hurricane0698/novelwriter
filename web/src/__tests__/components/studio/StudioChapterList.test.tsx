import { act, fireEvent, render, screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { StudioChapterList, type StudioChapterListItem } from '@/components/studio/rail/StudioChapterList'
import { UiLocaleProvider } from '@/contexts/UiLocaleContext'

const chapters: StudioChapterListItem[] = Array.from({ length: 1000 }, (_, index) => ({
  chapterNumber: index + 1, label: `Chapter ${index + 1}`,
}))
const props = {
  chapters, selectedChapterNumber: 3, onSelectChapter: vi.fn(), chapterCount: chapters.length,
  activeStage: null,
}
const wrapper = UiLocaleProvider
const chapter = (number: number) => screen.getByRole('button', { name: `Chapter ${number}`, exact: true })

describe('StudioChapterList', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    vi.spyOn(HTMLElement.prototype, 'clientHeight', 'get').mockReturnValue(420)
  })
  afterEach(() => {
    vi.restoreAllMocks()
    vi.unstubAllGlobals()
  })

  it('bounds the mounted rows for 1000 chapters while reaching the end by scrolling', () => {
    render(<StudioChapterList {...props} selectedChapterNumber={750} />, { wrapper })
    const list = screen.getByTestId('studio-rail-chapters')
    expect(within(list).getAllByRole('button').length).toBeLessThan(60)
    expect(chapter(750)).toBeInTheDocument()
    const viewport = screen.getByTestId('studio-chapter-viewport')
    fireEvent.scroll(viewport, { target: { scrollTop: 42000 - 420 } })
    expect(chapter(1000)).toBeInTheDocument()
    expect(within(list).queryByRole('button', { name: 'Chapter 1', exact: true })).not.toBeInTheDocument()
    expect(within(list).getAllByRole('button').length).toBeLessThan(60)
  })

  it('reveals route selection and preserves filtered search results and label changes', () => {
    const view = render(<StudioChapterList {...props} />, { wrapper })
    view.rerender(<StudioChapterList {...props} selectedChapterNumber={995} />)
    expect(chapter(995)).toHaveAttribute('aria-current', 'true')
    expect(screen.getByTestId('studio-chapter-viewport').scrollTop).toBeGreaterThan(40000)
    const filtered = chapters.filter(item => item.chapterNumber === 995 || item.chapterNumber === 1000)
    view.rerender(<StudioChapterList {...props} chapters={filtered} selectedChapterNumber={995} />)
    expect(screen.getAllByRole('button')).toHaveLength(2)
    expect(chapter(995)).toBeInTheDocument()
    expect(chapter(1000)).toBeInTheDocument()
    view.rerender(<StudioChapterList {...props} selectedChapterNumber={995} />)
    expect(chapter(995)).toBeInTheDocument()
    const renamed = chapters.map(item => item.chapterNumber === 995 ? { ...item, label: 'Revised chapter' } : item)
    view.rerender(<StudioChapterList {...props} chapters={renamed} selectedChapterNumber={995} />)
    expect(screen.getByRole('button', { name: 'Revised chapter' })).toBeInTheDocument()
  })

  it('navigates across windows with arrows, page keys, Home/End and Tab, then activates normally', async () => {
    const user = userEvent.setup()
    render(<><button>Before list</button><StudioChapterList {...props} /><button>After list</button></>, { wrapper })
    act(() => chapter(3).focus())
    fireEvent.keyDown(document.activeElement!, { key: 'End' })
    expect(chapter(1000)).toHaveFocus()
    await user.tab()
    expect(screen.getByRole('button', { name: 'After list' })).toHaveFocus()
    await user.tab({ shift: true })
    expect(chapter(1000)).toHaveFocus()
    fireEvent.keyDown(document.activeElement!, { key: 'Home' })
    expect(chapter(1)).toHaveFocus()
    await user.tab({ shift: true })
    expect(screen.getByRole('button', { name: 'Before list' })).toHaveFocus()
    await user.tab()
    expect(chapter(1)).toHaveFocus()
    fireEvent.keyDown(document.activeElement!, { key: 'PageDown' })
    expect(chapter(11)).toHaveFocus()
    fireEvent.keyDown(document.activeElement!, { key: 'ArrowDown' })
    expect(chapter(12)).toHaveFocus()
    await user.tab()
    expect(chapter(13)).toHaveFocus()
    await user.tab({ shift: true })
    expect(chapter(12)).toHaveFocus()
    fireEvent.keyDown(document.activeElement!, { key: 'PageUp' })
    expect(chapter(2)).toHaveFocus()
    fireEvent.keyDown(document.activeElement!, { key: 'ArrowUp' })
    expect(chapter(1)).toHaveFocus()
    await user.keyboard('{Enter}')
    expect(props.onSelectChapter).toHaveBeenCalledExactlyOnceWith(1)
  })

  it('retains keyboard focus when a pointer scrolls its row out of the visible window', () => {
    render(<StudioChapterList {...props} />, { wrapper })
    const focused = chapter(3)
    act(() => focused.focus())
    const viewport = screen.getByTestId('studio-chapter-viewport')
    fireEvent.scroll(viewport, { target: { scrollTop: 40000 } })
    expect(focused).toHaveFocus()
    expect(screen.getAllByRole('button').length).toBeLessThan(60)
    fireEvent.keyDown(focused, { key: 'ArrowDown' })
    expect(chapter(4)).toHaveFocus()
    expect(viewport.scrollTop).toBeLessThan(200)
  })

  it('keeps small lists fully rendered with ordinary keyboard tab order', async () => {
    const user = userEvent.setup()
    render(<StudioChapterList {...props} chapters={chapters.slice(0, 10)} chapterCount={10} />, { wrapper })
    expect(screen.getAllByRole('button')).toHaveLength(10)
    act(() => chapter(1).focus())
    await user.tab()
    expect(chapter(2)).toHaveFocus()
    await user.keyboard('{Enter}')
    expect(props.onSelectChapter).toHaveBeenCalledExactlyOnceWith(2)
  })

  it('updates the window after resize and releases both StrictMode observer lifetimes', () => {
    const callbacks: Array<() => void> = []
    const disconnect = vi.fn()
    vi.stubGlobal('ResizeObserver', class {
      constructor(callback: () => void) { callbacks.push(callback) }
      observe() {}
      disconnect = disconnect
    })
    let height = 420
    vi.spyOn(HTMLElement.prototype, 'clientHeight', 'get').mockImplementation(() => height)
    const view = render(<StudioChapterList {...props} />, { wrapper, reactStrictMode: true })
    const count = screen.getAllByRole('button').length
    expect(callbacks).toHaveLength(2)
    expect(disconnect).toHaveBeenCalledTimes(1)
    act(() => {
      height = 840
      callbacks.at(-1)!()
    })
    expect(screen.getAllByRole('button')).toHaveLength(count + 10)
    expect(chapter(3)).toBeInTheDocument()
    view.unmount()
    expect(disconnect).toHaveBeenCalledTimes(2)
  })
})
