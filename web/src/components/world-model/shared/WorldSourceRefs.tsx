import '@/lib/uiMessagePacks/copilot'
import { useUiLocale } from '@/contexts/UiLocaleContext'
import { TextSourceLink } from '@/components/novel-copilot/TextSourceLink'
import type { WorldSourceRef } from '@/types/api'

export function WorldSourceRefs({ novelId, sources }: { novelId: number; sources?: WorldSourceRef[] }) {
  const { t } = useUiLocale()
  if (!sources?.length) return null
  const changed = sources.some((source) => source.status !== 'current')
  return <details className="mt-2 text-xs leading-6 text-muted-foreground" data-testid="world-source-refs">
    <summary className="cursor-pointer">{t(changed ? 'review.sourceChanged' : 'review.sourceCurrent')}</summary>
    {changed && <p>{t('review.sourceNote')}</p>}
    {sources.map((source, index) => <div key={index} className="mt-2 border-l-2 border-border pl-3">
      <p>{source.quote}</p>
      {source.status === 'missing' ? <span>{t('review.sourceMissing')}</span>
        : <TextSourceLink novelId={novelId} source={source} />}
    </div>)}
  </details>
}
