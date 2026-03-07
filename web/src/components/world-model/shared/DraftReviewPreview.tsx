import { cn } from '@/lib/utils'
import { Button } from '@/components/ui/button'
import { useWorldEntities } from '@/hooks/world/useEntities'
import { useWorldRelationships } from '@/hooks/world/useRelationships'
import { useWorldSystems } from '@/hooks/world/useSystems'

export type DraftReviewKind = 'entities' | 'relationships' | 'systems'

export function DraftReviewPreview({
  novelId,
  onOpen,
  className,
}: {
  novelId: number
  onOpen: (kind?: DraftReviewKind) => void
  className?: string
}) {
  const { data: draftEntities = [] } = useWorldEntities(novelId, { status: 'draft' })
  const { data: draftRelationships = [] } = useWorldRelationships(novelId, { status: 'draft' })
  const { data: draftSystems = [] } = useWorldSystems(novelId, { status: 'draft' })

  const total = draftEntities.length + draftRelationships.length + draftSystems.length

  return (
    <div
      className={cn(
        'rounded-xl border border-[var(--nw-glass-border)] bg-[var(--nw-glass-bg)] backdrop-blur-2xl p-3 space-y-2',
        className,
      )}
      data-testid="draft-review-preview"
    >
      <div className="flex items-center gap-2">
        <div className="text-sm font-medium text-foreground">草稿审核</div>
        <span className="ml-auto rounded-full border border-[var(--nw-glass-border)] px-2 py-0.5 text-xs tabular-nums text-[hsl(var(--color-status-draft))]">
          {total}
        </span>
      </div>

      <div className="space-y-1">
        <KindRow label="实体" count={draftEntities.length} onClick={() => onOpen('entities')} />
        <KindRow label="关系" count={draftRelationships.length} onClick={() => onOpen('relationships')} />
        <KindRow label="体系" count={draftSystems.length} onClick={() => onOpen('systems')} />
      </div>

      <Button
        variant="outline"
        size="sm"
        className="w-full h-8 text-xs border-[var(--nw-glass-border)] bg-transparent hover:bg-[var(--nw-glass-bg-hover)]"
        onClick={() => onOpen()}
      >
        查看全部
      </Button>
    </div>
  )
}

function KindRow({ label, count, onClick }: { label: string; count: number; onClick: () => void }) {
  return (
    <button
      type="button"
      className={cn(
        'w-full flex items-center gap-2 rounded-lg px-2 py-1 text-xs transition-colors',
        count > 0
          ? 'text-muted-foreground hover:text-foreground hover:bg-[var(--nw-glass-bg-hover)]'
          : 'text-muted-foreground/60',
      )}
      onClick={onClick}
      disabled={count === 0}
    >
      <span className="truncate">{label}</span>
      <span className="ml-auto tabular-nums">{count}</span>
    </button>
  )
}
