import { X } from 'lucide-react'
import { cn } from '@/lib/utils'
import { useUiLocale } from '@/contexts/UiLocaleContext'
import type { CopilotRunStatus, NovelCopilotSession } from '@/types/copilot'
import { getCopilotScopeLabel } from './novelCopilotHelpers'
import { getCopilotRunStatusMeta } from './novelCopilotView'

export function NovelCopilotSessionStrip({ sessions, focusedSessionId, getSessionStatus, onFocusSession, onRemoveSession }: {
  sessions: NovelCopilotSession[]
  focusedSessionId: string | null
  getSessionStatus: (sessionId: string) => CopilotRunStatus | null
  onFocusSession: (sessionId: string) => void
  onRemoveSession: (sessionId: string) => void
}) {
  const { locale, t } = useUiLocale()
  if (sessions.length < 2) return null

  return (
    <nav className="flex shrink-0 gap-2 overflow-x-auto border-b border-[var(--nw-copilot-border)] px-4 py-2"
      aria-label={t('copilot.sessionStrip.title')}
      data-testid="novel-copilot-session-strip">
      {sessions.map((session) => {
        const isFocused = session.sessionId === focusedSessionId
        const status = getCopilotRunStatusMeta(getSessionStatus(session.sessionId), locale)
        return (
          <div key={session.sessionId} data-testid={`novel-copilot-session-${session.sessionId}`}
            data-state={isFocused ? 'active' : 'inactive'}
            className={cn('flex shrink-0 items-center rounded-lg', isFocused ? 'bg-foreground/[0.07]' : 'hover:bg-foreground/[0.04]')}>
            <button type="button" aria-pressed={isFocused} onClick={() => onFocusSession(session.sessionId)}
              title={`${getCopilotScopeLabel(session.prefill, locale)} · ${status.label}`}
              className="flex max-w-[190px] items-center gap-2 px-3 py-2 text-left text-xs">
              <span className={cn('h-1.5 w-1.5 shrink-0 rounded-full', status.dotClassName)} />
              <span className="truncate">{session.displayTitle}</span>
            </button>
            <button type="button" onClick={() => onRemoveSession(session.sessionId)}
              aria-label={t('copilot.sessionStrip.close')} data-role="close-session"
              className="mr-1 rounded-md p-1.5 text-muted-foreground hover:bg-foreground/10 hover:text-foreground">
              <X className="h-3 w-3" />
            </button>
          </div>
        )
      })}
    </nav>
  )
}
