import { useState } from 'react'
import { SystemList } from '@/components/world-model/systems/SystemList'
import { SystemEditor } from '@/components/world-model/systems/SystemEditor'
import { useWorldSystem } from '@/hooks/world/useSystems'
import type { WorldSystem } from '@/types/api'
import type { DraftReviewKind } from '@/components/world-model/shared/DraftReviewPreview'

export function SystemsTab({
  novelId,
  onOpenDraftReview,
}: {
  novelId: number
  onOpenDraftReview: (kind?: DraftReviewKind) => void
}) {
  const [selectedId, setSelectedId] = useState<number | null>(null)
  const { data: system } = useWorldSystem(novelId, selectedId)

  return (
    <div className="flex h-full min-h-0">
      <div className="w-[280px] shrink-0 border-r border-[var(--nw-glass-border)] bg-[var(--nw-glass-bg)] backdrop-blur-2xl overflow-hidden">
        <SystemList
          novelId={novelId}
          selectedId={selectedId}
          onSelect={(s: WorldSystem) => setSelectedId(s.id)}
          onOpenDraftReview={onOpenDraftReview}
        />
      </div>
      <div className="flex-1 min-w-0 overflow-y-auto">
        {selectedId && system ? (
          <SystemEditor novelId={novelId} system={system} onBack={() => setSelectedId(null)} />
        ) : (
          <div className="h-full flex items-center justify-center text-muted-foreground">
            选择一个体系开始编辑
          </div>
        )}
      </div>
    </div>
  )
}
