const statusTitle = document.querySelector('#status-title')
const statusSummary = document.querySelector('#status-summary')
const failureActions = document.querySelector('#failure-actions')
const openLogs = document.querySelector('#open-logs')
const quit = document.querySelector('#quit')

function invoke(command) {
  const tauri = window.__TAURI__
  if (!tauri?.core?.invoke) {
    throw new Error('Tauri IPC is unavailable on the local shell page.')
  }
  return tauri.core.invoke(command)
}

function renderFailure(summary) {
  statusTitle.textContent = '启动失败'
  statusSummary.textContent = summary
  failureActions.hidden = false
}

const failureSummary = new URL(window.location.href).searchParams.get('failure')
if (failureSummary) {
  renderFailure(failureSummary)
}

openLogs.addEventListener('click', () => {
  void invoke('open_logs')
})

quit.addEventListener('click', () => {
  void invoke('quit')
})
