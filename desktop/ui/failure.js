const statusTitle = document.querySelector('#status-title')
const statusSummary = document.querySelector('#status-summary')
const failureActions = document.querySelector('#failure-actions')
const openLogs = document.querySelector('#open-logs')
const quit = document.querySelector('#quit')
const startupStatusPollIntervalMs = 250
let failureRendered = false

function invoke(command) {
  const tauri = window.__TAURI__
  if (!tauri?.core?.invoke) {
    throw new Error('Tauri IPC is unavailable on the local shell page.')
  }
  return tauri.core.invoke(command)
}

function renderFailure(summary) {
  failureRendered = true
  statusTitle.textContent = '启动失败'
  statusSummary.textContent = summary
  failureActions.hidden = false
}

const failureSummary = new URL(window.location.href).searchParams.get('failure')
if (failureSummary) {
  renderFailure(failureSummary)
} else {
  // Startup can fail after this script's first IPC read but before the runtime
  // navigates to the application. Keep reading while this local shell remains
  // loaded so that early failures cannot leave a permanent "正在启动" page.
  watchStartupFailure()
}

async function watchStartupFailure() {
  while (!failureRendered) {
    try {
      const summary = await invoke('startup_status')
      if (summary) {
        renderFailure(summary)
        return
      }
    } catch {
      // The next poll may succeed if IPC injection is still settling.
    }
    await new Promise((resolve) => window.setTimeout(resolve, startupStatusPollIntervalMs))
  }
}

openLogs.addEventListener('click', () => {
  void invoke('open_logs')
})

quit.addEventListener('click', () => {
  void invoke('quit')
})
