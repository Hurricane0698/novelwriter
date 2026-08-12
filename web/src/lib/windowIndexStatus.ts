import type { WindowIndexState } from '@/types/api'
import { readDocumentUiLocale } from '@/lib/uiLocale'
import { translateUiMessage, type UiLocale, type UiMessageKey } from '@/lib/uiMessages'

export interface WindowIndexStatusMeta {
  text: string
  tone: 'muted' | 'success' | 'warning'
  requiresFallback: boolean
}

const ACTIVE_READINESS_STATES = new Set(['accepting', 'processing'])
const WINDOW_INDEX_ACTIVE_POLL_INTERVAL_MS = 2000

function localeOrDefault(locale?: UiLocale): UiLocale {
  return locale ?? readDocumentUiLocale() ?? 'zh'
}

function assertNeverReadiness(readiness: never): never {
  throw new Error(`Unsupported window index readiness: ${String(readiness)}`)
}

export function isWindowIndexRebuilding(state: WindowIndexState | null | undefined): boolean {
  return Boolean(state?.readiness && ACTIVE_READINESS_STATES.has(state.readiness))
}

export function getWindowIndexPollingInterval(
  state: WindowIndexState | null | undefined,
): number | false {
  return isWindowIndexRebuilding(state) ? WINDOW_INDEX_ACTIVE_POLL_INTERVAL_MS : false
}

function resolveWindowIndexStatusMeta(
  state: WindowIndexState | null | undefined,
  locale: UiLocale,
  keys: {
    preparing: UiMessageKey
    organizing: UiMessageKey
    ready: UiMessageKey
    pending: UiMessageKey
    missing: UiMessageKey
    failed: UiMessageKey
  },
): WindowIndexStatusMeta {
  if (!state) {
    return {
      text: translateUiMessage(locale, keys.preparing),
      tone: 'muted',
      requiresFallback: false,
    }
  }

  // Persisted clients and pre-readiness API fixtures may still carry only the
  // legacy `status` field. Normalize that shape at the boundary instead of
  // letting an absent runtime value reach the exhaustive switch below.
  const capabilities = state.capabilities ?? {
    chapters_available: false,
    whole_book_index_available: state.status === 'fresh',
    bootstrap_available: state.status === 'fresh',
    recent_fallback_only: state.status !== 'fresh',
  }
  const readiness = state.readiness ?? (
    state.status === 'fresh'
      ? 'ready'
      : state.status === 'failed'
        ? 'failed_retryable'
        : capabilities.chapters_available
          ? 'degraded_ready'
          : 'accepting'
  )

  if (readiness === 'accepting') {
    return {
      text: translateUiMessage(locale, keys.preparing),
      tone: 'muted',
      requiresFallback: false,
    }
  }

  if (readiness === 'processing') {
    if (capabilities.chapters_available) {
      return {
        text: translateUiMessage(locale, keys.organizing),
        tone: 'muted',
        requiresFallback: true,
      }
    }
    return {
      text: translateUiMessage(locale, keys.preparing),
      tone: 'muted',
      requiresFallback: false,
    }
  }

  if (readiness === 'ready') {
    return {
      text: translateUiMessage(locale, keys.ready),
      tone: 'success',
      requiresFallback: false,
    }
  }

  if (readiness === 'failed_retryable' || readiness === 'failed_terminal') {
    return {
      text: translateUiMessage(locale, keys.failed),
      tone: 'warning',
      requiresFallback: Boolean(capabilities.recent_fallback_only),
    }
  }

  if (readiness === 'degraded_ready') {
    if (state.status === 'failed') {
      return {
        text: translateUiMessage(locale, keys.failed),
        tone: 'warning',
        requiresFallback: true,
      }
    }

    if (capabilities.recent_fallback_only) {
      return {
        text: translateUiMessage(locale, state.status === 'stale' ? keys.pending : keys.missing),
        tone: 'warning',
        requiresFallback: true,
      }
    }

    return {
      text: translateUiMessage(locale, keys.missing),
      tone: 'warning',
      requiresFallback: true,
    }
  }

  return assertNeverReadiness(readiness)
}

export function getWindowIndexBootstrapStatusMeta(
  state: WindowIndexState | null | undefined,
  locale?: UiLocale,
): WindowIndexStatusMeta {
  const effectiveLocale = localeOrDefault(locale)
  return resolveWindowIndexStatusMeta(state, effectiveLocale, {
    preparing: 'worldModel.windowIndex.bootstrap.preparingContent',
    organizing: 'worldModel.windowIndex.bootstrap.organizingChapters',
    ready: 'worldModel.windowIndex.bootstrap.ready',
    pending: 'worldModel.windowIndex.bootstrap.pendingSync',
    missing: 'worldModel.windowIndex.bootstrap.missing',
    failed: 'worldModel.windowIndex.bootstrap.failed',
  })
}

export function getWindowIndexCopilotStatusMeta(
  state: WindowIndexState | null | undefined,
  locale?: UiLocale,
): WindowIndexStatusMeta {
  const effectiveLocale = localeOrDefault(locale)
  return resolveWindowIndexStatusMeta(state, effectiveLocale, {
    preparing: 'worldModel.windowIndex.copilot.preparingContent',
    organizing: 'worldModel.windowIndex.copilot.organizingContent',
    ready: 'worldModel.windowIndex.copilot.ready',
    pending: 'worldModel.windowIndex.copilot.pendingSync',
    missing: 'worldModel.windowIndex.copilot.missing',
    failed: 'worldModel.windowIndex.copilot.failed',
  })
}
