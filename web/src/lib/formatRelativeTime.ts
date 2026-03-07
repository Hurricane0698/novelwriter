export function formatRelativeTime(dateStr: string): string {
  const ms = new Date(dateStr).getTime()
  if (!Number.isFinite(ms)) return '刚刚'

  const diff = Date.now() - ms
  const mins = Math.floor(diff / 60000)

  if (mins < 1) return '刚刚'
  if (mins < 60) return `${mins} 分钟前`

  const hrs = Math.floor(mins / 60)
  if (hrs < 24) return `${hrs} 小时前`

  const days = Math.floor(hrs / 24)
  if (days === 1) return '昨天'
  if (days < 7) return `${days} 天前`

  const weeks = Math.floor(days / 7)
  if (weeks < 5) return `${weeks} 周前`

  return `${Math.floor(days / 30)} 月前`
}
