import { useSyncExternalStore } from 'react'
import { createPortal } from 'react-dom'
import { getDesktopExitState, resolveDesktopExit, saveBeforeDesktopExit, subscribeDesktopExit } from '@/lib/desktopExit'
import { useUiLocale } from '@/contexts/UiLocaleContext'

export function DesktopExitGuard() {
  const { locale } = useUiLocale()
  const state = useSyncExternalStore(subscribeDesktopExit, getDesktopExitState)
  if (state.phase === 'idle') return null
  const en = locale.startsWith('en')
  const failed = state.phase === 'failed'
  return createPortal(
    <div className="fixed inset-0 z-[200] flex items-center justify-center bg-black/40 p-6">
      <div role="alertdialog" aria-modal="true" aria-labelledby="desktop-exit-title" className="max-w-md rounded-xl border bg-background p-6 text-foreground shadow-xl">
        <h2 id="desktop-exit-title" className="text-lg font-semibold">{failed
          ? (en ? 'Could not save before quitting' : '退出前保存失败')
          : (en ? 'Saving before quitting…' : '正在保存，即将退出…')}</h2>
        <p className="my-4 text-sm">{failed
          ? (en ? 'Your text is still here. Retry or continue editing. Discarding will lose unsaved changes.' : '正文仍保留在编辑器中。可以重试或继续编辑；放弃保存会丢失未保存的修改。')
          : (en ? 'Waiting for all pending saves to finish.' : '正在等待所有保存请求完成。')}</p>
        <div className="flex flex-wrap gap-3 text-sm">
          {failed && <button className="rounded border px-3 py-2" onClick={() => { void saveBeforeDesktopExit() }}>{en ? 'Retry' : '重试保存'}</button>}
          <button className="rounded border px-3 py-2" onClick={() => { void resolveDesktopExit('cancel') }}>{en ? 'Continue editing' : '继续编辑'}</button>
          {failed && <button className="rounded border px-3 py-2 text-destructive" onClick={() => { void resolveDesktopExit('discard') }}>{en ? 'Discard and quit' : '放弃保存并退出'}</button>}
        </div>
      </div>
    </div>, document.body,
  )
}
