import { act, fireEvent, render, screen, cleanup } from '@testing-library/react'
import { afterEach, beforeEach, expect, it, vi } from 'vitest'
import { DesktopExitGuard } from '@/components/DesktopExitGuard'
import { UiLocaleProvider } from '@/contexts/UiLocaleContext'
import { installDesktopExit, getDesktopExitState } from '@/lib/desktopExit'
import { useStudioChapterEditor } from '@/hooks/novel/useStudioChapterEditor'

const invoke = vi.fn()
let uninstall: () => void
let root: HTMLDivElement

function Editor({ save }: { save: (update: { content: string }) => Promise<void> }) {
  const editor = useStudioChapterEditor({ novelId: 7, chapterNumber: 1, locationKey: 'chapter', chapterContent: 'Original', saveChapter: save })
  return <><textarea aria-label="Body" value={editor.editorContent} onChange={event => editor.handleEditorChange(event.target.value)} /><DesktopExitGuard /></>
}

beforeEach(() => {
  vi.useFakeTimers()
  invoke.mockReset().mockResolvedValue(true)
  Object.defineProperty(window, '__TAURI__', { configurable: true, value: { core: { invoke } } })
  root = document.createElement('div')
  root.id = 'root'
  document.body.append(root)
  uninstall = installDesktopExit()
})
afterEach(() => {
  cleanup()
  uninstall()
  root.remove()
  Reflect.deleteProperty(window, '__TAURI__')
  vi.useRealTimers()
})

function mount(save: (update: { content: string }) => Promise<void>) {
  render(<UiLocaleProvider><Editor save={save} /></UiLocaleProvider>, { container: root })
  fireEvent.change(screen.getByLabelText('Body'), { target: { value: 'Last paragraph' } })
}
async function quit(requestId = 1) {
  await act(async () => { window.dispatchEvent(new CustomEvent('novwr:prepare-exit', { detail: { requestId } })) })
}

it('flushes immediately on quit, freezes editing and waits for the API acknowledgement despite repeated quit', async () => {
  let finish!: () => void
  const save = vi.fn(() => new Promise<void>(resolve => { finish = resolve }))
  mount(save)
  expect(save).not.toHaveBeenCalled()
  await quit()
  expect(save).toHaveBeenCalledWith({ content: 'Last paragraph' })
  expect(root.inert).toBe(true)
  await quit()
  await quit(2)
  expect(save).toHaveBeenCalledTimes(1)
  expect(invoke).not.toHaveBeenCalled()
  await act(async () => { finish() })
  expect(invoke).toHaveBeenCalledExactlyOnceWith('complete_exit', { requestId: 1, decision: 'saved' })
})

it('joins an already running autosave before authorizing native shutdown', async () => {
  let finish!: () => void
  const save = vi.fn(() => new Promise<void>(resolve => { finish = resolve }))
  mount(save)
  await act(async () => { await vi.advanceTimersByTimeAsync(3000) })
  await quit()
  expect(invoke).not.toHaveBeenCalled()
  expect(save).toHaveBeenCalledTimes(1)
  await act(async () => { finish() })
  expect(invoke).toHaveBeenCalledWith('complete_exit', { requestId: 1, decision: 'saved' })
})

it('keeps failed text open and retries it before permitting quit', async () => {
  const save = vi.fn().mockRejectedValueOnce(new Error('write failed')).mockResolvedValue(undefined)
  mount(save)
  await quit()
  expect(getDesktopExitState().phase).toBe('failed')
  expect(invoke).not.toHaveBeenCalled()
  expect(screen.getByRole('alertdialog')).toHaveTextContent('退出前保存失败')
  await act(async () => { fireEvent.click(screen.getByRole('button', { name: '重试保存' })) })
  expect(save).toHaveBeenCalledTimes(2)
  expect(invoke).toHaveBeenCalledWith('complete_exit', { requestId: 1, decision: 'saved' })
})

it('requires explicit discard after failure and allows continuing to edit', async () => {
  mount(vi.fn().mockRejectedValue(new Error('offline')))
  await quit()
  await act(async () => { fireEvent.click(screen.getByRole('button', { name: '继续编辑' })) })
  expect(root.inert).toBe(false)
  expect(invoke).toHaveBeenLastCalledWith('complete_exit', { requestId: 1, decision: 'cancel' })
  expect(screen.getByLabelText('Body')).toHaveValue('Last paragraph')
  await quit(2)
  await act(async () => { fireEvent.click(screen.getByRole('button', { name: '放弃保存并退出' })) })
  expect(invoke).toHaveBeenLastCalledWith('complete_exit', { requestId: 2, decision: 'discard' })
})

it('ignores a save completion after native timeout cancellation', async () => {
  let finish!: () => void
  mount(() => new Promise<void>(resolve => { finish = resolve }))
  await quit()
  await act(async () => { window.dispatchEvent(new CustomEvent('novwr:cancel-exit', { detail: { requestId: 1 } })) })
  expect(root.inert).toBe(false)
  await act(async () => { finish() })
  expect(invoke).not.toHaveBeenCalled()
})

it('does not race a pending continue-editing acknowledgement with save success', async () => {
  let finish!: () => void
  let cancelConfirmed!: () => void
  mount(() => new Promise<void>(resolve => { finish = resolve }))
  await quit()
  invoke.mockImplementation(() => new Promise<boolean>(resolve => { cancelConfirmed = () => resolve(true) }))
  await act(async () => { fireEvent.click(screen.getByRole('button', { name: '继续编辑' })) })
  await act(async () => { finish() })
  expect(invoke).toHaveBeenCalledExactlyOnceWith('complete_exit', { requestId: 1, decision: 'cancel' })
  expect(root.inert).toBe(true)
  await act(async () => { cancelConfirmed() })
  expect(root.inert).toBe(false)
})
