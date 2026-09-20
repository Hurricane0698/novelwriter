import { Link, useNavigate } from 'react-router-dom'
import { useUiLocale } from '@/contexts/UiLocaleContext'

export function TextSourceLink({ novelId, source, beforeNavigate }: {
  novelId: number; source?: Record<string, unknown> | null; beforeNavigate?: () => Promise<void>
}) {
  const { t } = useUiLocale()
  const navigate = useNavigate()
  if (!source || typeof source.chapter_number !== 'number') return null
  if (source.kind === 'continuation' && typeof source.id === 'number') return <Link
    className="text-xs text-muted-foreground underline underline-offset-4 hover:text-foreground"
    to={`/novel/${novelId}?stage=results&continuations=0:${source.id}`}>
    {t('review.current')} · {source.id}
  </Link>
  const params = new URLSearchParams({ chapter: String(source.chapter_number) })
  if (typeof source.start_pos === 'number') params.set('sourceStart', String(source.start_pos))
  if (typeof source.end_pos === 'number') params.set('sourceEnd', String(source.end_pos))
  if (typeof source.content_hash === 'string') params.set('sourceHash', source.content_hash)
  const url = `/novel/${novelId}?${params}`
  return <Link className="text-xs text-muted-foreground underline underline-offset-4 hover:text-foreground"
    onClick={beforeNavigate ? (event) => { event.preventDefault(); void beforeNavigate().then(() => navigate(url)).catch(() => undefined) } : undefined}
    to={url}>
    {t('review.source')} · {source.chapter_number}
  </Link>
}
