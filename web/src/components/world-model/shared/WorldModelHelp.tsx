import '@/lib/uiMessagePacks/copilot'
import { useUiLocale } from '@/contexts/UiLocaleContext'

export function WorldModelHelp({ kind, empty = false }: { kind: 'entity' | 'relationship' | 'system'; empty?: boolean }) {
  const { t } = useUiLocale()
  const explanation = t(kind === 'entity' ? 'review.entityHelp' : kind === 'relationship' ? 'review.relationshipHelp' : 'review.systemHelp')
  return <div className="mb-4 space-y-2 text-xs leading-6 text-muted-foreground">
    <p>{explanation}</p>
    <details open={empty}><summary className="cursor-pointer hover:text-foreground">{t('review.worldTitle')}</summary>
      <p className="mt-2">{t(kind === 'entity' ? 'review.entityExample' : kind === 'relationship' ? 'review.relationshipExample' : 'review.systemExample')}</p>
      <p className="mt-2">{t('review.materialHelp')}</p>
    </details>
  </div>
}
