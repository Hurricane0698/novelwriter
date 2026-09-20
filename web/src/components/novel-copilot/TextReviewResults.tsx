import { useRef, useState } from 'react'
import { useUiLocale } from '@/contexts/UiLocaleContext'
import { NwButton } from '@/components/ui/nw-button'
import { copilotApi } from '@/services/copilotApi'
import type { CopilotRun, NovelCopilotSession, CopilotSuggestionTarget } from '@/types/copilot'
import { useNovelCopilot } from './NovelCopilotContext'
import { NovelCopilotSuggestionCard } from './NovelCopilotSuggestionCard'
import { TextSourceLink } from './TextSourceLink'

function editsOverlap(run: CopilotRun, selected: string[]) {
  const edits = run.suggestions.filter((s) => selected.includes(s.suggestion_id))
    .flatMap((s) => s.apply?.type === 'replace_text' ? [s.apply.data] : [])
    .sort((a, b) => a.start - b.start)
  return edits.some((edit, index) => index > 0 && edits[index - 1].end > edit.start)
}

export function TextReviewResults({ run, session, onLocateTarget }: {
  run: CopilotRun; session: NovelCopilotSession; onLocateTarget?: (target: CopilotSuggestionTarget) => void
}) {
  const { t } = useUiLocale()
  const { getTextTarget, resolveBackendSessionId, refreshRun, applySuggestions, dismissSuggestions, textUndo, setTextUndo } = useNovelCopilot()
  const [selected, setSelected] = useState<string[]>([])
  const [busy, setBusy] = useState(false)
  const busyRef = useRef(false)
  const [error, setError] = useState('')
  const undo = textUndo?.runId === run.run_id ? textUndo.change : null
  const metadata = run.text_review!
  const binding = getTextTarget(metadata.target)
  const overlap = editsOverlap(run, selected)
  const blocked = busy || metadata.stale || metadata.closed || !binding

  const operate = async (operation: () => Promise<void>) => {
    if (busyRef.current) return
    busyRef.current = true
    setBusy(true)
    setError('')
    try { await operation() } catch (error) {
      setError(t(error instanceof Error && error.message === 'Text changed after apply'
        ? 'review.undoChanged' : 'review.failed'))
      await refreshRun(session.sessionId, run.run_id).catch(() => undefined)
    } finally { busyRef.current = false; setBusy(false) }
  }

  const apply = () => void operate(async () => {
    if (!binding || blocked || overlap || !metadata.target.content_hash) return
    const backendId = await resolveBackendSessionId(session.sessionId)
    const change = await binding.write(() => copilotApi.applyText(
      session.novelId, backendId, run.run_id, selected, metadata.target.content_hash!,
    ))
    setTextUndo({ runId: run.run_id, change })
    setSelected([])
    await refreshRun(session.sessionId, run.run_id)
  })

  return <section className="space-y-3" data-testid="text-review-results">
    <p className="text-xs leading-6 text-muted-foreground">{metadata.coverage}</p>
    <details className="border-t border-border/60 py-3 text-xs text-muted-foreground">
      <summary className="cursor-pointer">{t('review.coverage')}</summary>
      <p className="mt-2 leading-6">{t('review.budget')}</p>
      <div className="mt-2 space-y-2">{run.evidence.map((evidence) => <div key={evidence.evidence_id}>
        <span className="mr-2">{evidence.title}</span>
        <TextSourceLink novelId={session.novelId} source={evidence.source_ref}
          beforeNavigate={binding ? async () => { await binding.prepare() } : undefined} />
        {evidence.source_type === 'world_setting' && onLocateTarget && <button type="button" className="text-xs underline underline-offset-4"
          onClick={() => void operate(async () => {
            if (binding) await binding.prepare()
            const ref = evidence.source_ref
            const resource = ref?.resource === 'attribute' ? 'entity' : ref?.resource
            const values = ref?.values as Record<string, unknown> | undefined
            const id = ref?.resource === 'attribute' ? values?.entity_id : ref?.id
            if ((resource === 'entity' || resource === 'relationship' || resource === 'system') && typeof id === 'number') {
              onLocateTarget({ resource, resource_id: id, label: evidence.title,
                tab: resource === 'entity' ? 'entities' : resource === 'relationship' ? 'relationships' : 'systems' })
            }
          })}>{t('copilot.suggestion.locate')}</button>}
      </div>)}</div>
    </details>
    {metadata.closed ? <p className="text-xs text-muted-foreground">{t('review.closed')}</p>
      : metadata.stale ? <p role="status" className="text-xs text-amber-600 dark:text-amber-300">{t('review.stale')}</p>
        : !binding ? <p className="text-xs text-muted-foreground">{t('review.unavailable')}</p> : null}
    {run.suggestions.filter((s) => s.status !== 'dismissed').map((suggestion) => <NovelCopilotSuggestionCard
      key={suggestion.suggestion_id} suggestion={suggestion}
      mode={suggestion.status === 'applied' ? 'applied' : 'pending'}
      isApplying={Boolean(blocked)}
      selection={metadata.action === 'review_text' ? {
        checked: selected.includes(suggestion.suggestion_id), disabled: Boolean(blocked) ||
          (!selected.includes(suggestion.suggestion_id) && editsOverlap(run, [...selected, suggestion.suggestion_id])),
        onChange: () => setSelected((ids) => ids.includes(suggestion.suggestion_id)
          ? ids.filter((id) => id !== suggestion.suggestion_id) : [...ids, suggestion.suggestion_id]),
      } : undefined}
      onApply={(id) => void operate(async () => {
        if (!binding || blocked) return
        await binding.withSavedText(async () => { await applySuggestions(session.sessionId, run.run_id, [id]) })
        await refreshRun(session.sessionId, run.run_id)
      })}
      onDismiss={(id) => {
        setSelected((ids) => ids.filter((value) => value !== id))
        void dismissSuggestions(session.sessionId, run.run_id, [id])
      }}
    />)}
    {overlap && <p role="alert" className="text-xs text-amber-600 dark:text-amber-300">{t('review.overlap')}</p>}
    {error && <p role="alert" className="text-xs text-destructive">{error}</p>}
    {metadata.action === 'review_text' && !metadata.closed && <NwButton variant="accent" className="px-3 py-2 text-xs"
      onClick={apply} disabled={Boolean(blocked) || selected.length === 0 || overlap}>{t('review.apply')}</NwButton>}
    {undo && <NwButton variant="glass" className="px-3 py-2 text-xs" disabled={busy || !binding}
      onClick={() => void operate(async () => {
        if (!binding) return
        await binding.restore(undo.before_content, undo.content_hash)
        setTextUndo(null)
        await refreshRun(session.sessionId, run.run_id)
      })}>{t('review.undo')}</NwButton>}
  </section>
}
