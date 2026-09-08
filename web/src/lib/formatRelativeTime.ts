import { translateUiMessage, type UiLocale } from '@/lib/uiMessages'
import { parseApiTimestamp } from '@/lib/apiTimestamp'

export function formatRelativeTime(dateStr: string, locale: UiLocale = 'zh'): string {
  const ms = parseApiTimestamp(dateStr)
  if (!Number.isFinite(ms)) return translateUiMessage(locale, 'time.justNow')

  const diff = Date.now() - ms
  const mins = Math.floor(diff / 60000)

  if (mins < 1) return translateUiMessage(locale, 'time.justNow')
  if (mins < 60) return translateUiMessage(locale, 'time.minutesAgo', { count: mins })

  const hrs = Math.floor(mins / 60)
  if (hrs < 24) return translateUiMessage(locale, 'time.hoursAgo', { count: hrs })

  const days = Math.floor(hrs / 24)
  if (days === 1) return translateUiMessage(locale, 'time.yesterday')
  if (days < 7) return translateUiMessage(locale, 'time.daysAgo', { count: days })

  const weeks = Math.floor(days / 7)
  if (weeks < 5) return translateUiMessage(locale, 'time.weeksAgo', { count: weeks })

  return translateUiMessage(locale, 'time.monthsAgo', { count: Math.floor(days / 30) })
}
