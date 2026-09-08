import { Component, type ReactNode } from 'react'

export class AppErrorBoundary extends Component<{ children: ReactNode }, { failed: boolean }> {
  state = { failed: false }

  static getDerivedStateFromError() {
    return { failed: true }
  }

  render() {
    if (!this.state.failed) return this.props.children
    const english = document.documentElement.lang.startsWith('en')
    return (
      <main role="alert" className="mx-auto max-w-xl p-8">
        <h1 className="text-xl font-semibold">{english ? 'The page could not load' : '页面未能加载'}</h1>
        <p className="my-4">{english
          ? 'Reload the page. If this keeps happening in the desktop app, update Microsoft Edge WebView2 and reopen NovWr.'
          : '请重新加载页面。若桌面版仍无法打开，请更新 Microsoft Edge WebView2 后重启 NovWr。'}</p>
        <button type="button" className="underline" onClick={() => window.location.reload()}>
          {english ? 'Reload page' : '重新加载页面'}
        </button>
      </main>
    )
  }
}
