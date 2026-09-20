import { useState } from 'react'
import { WorldModelHelp } from '@/components/world-model/shared/WorldModelHelp'
import { SystemNavigator } from '@/components/atlas/systems/SystemNavigator'
import { SystemEditor } from '@/components/world-model/systems/SystemEditor'
import { useWorldSystem } from '@/hooks/world/useSystems'
import { useUiLocale } from '@/contexts/UiLocaleContext'
import type { WorldSystem } from '@/types/api'
import type { DraftReviewKind } from '@/components/atlas/review/DraftReviewSummaryCard'

export function SystemsWorkspace({
  novelId,
  onOpenDraftReview,
  selectedId: selectedIdProp,
  onSelectSystem,
}: {
  novelId: number
  onOpenDraftReview: (kind?: DraftReviewKind) => void
  selectedId?: number | null
  onSelectSystem?: (systemId: number) => void
}) {
  const { t } = useUiLocale()
  const [selectedIdInternal, setSelectedIdInternal] = useState<number | null>(null)
  const selectedId = selectedIdProp ?? selectedIdInternal
  const { data: system } = useWorldSystem(novelId, selectedId)

  const handleSelect = (nextSystem: WorldSystem) => {
    if (onSelectSystem) {
      onSelectSystem(nextSystem.id)
      return
    }
    setSelectedIdInternal(nextSystem.id)
  }

  return (
    <div className="flex h-full min-h-0">
      <div className="w-[280px] shrink-0 border-r border-[var(--nw-glass-border)] bg-[var(--nw-glass-bg)] backdrop-blur-2xl overflow-hidden">
        <SystemNavigator
          novelId={novelId}
          selectedId={selectedId}
          onSelect={handleSelect}
          onOpenDraftReview={onOpenDraftReview}
        />
      </div>
      <div className="flex-1 min-w-0 overflow-y-auto">
        {selectedId && system ? (
          <SystemEditor novelId={novelId} system={system} onBack={() => setSelectedIdInternal(null)} />
        ) : (
          <div className="h-full flex flex-col items-center justify-center gap-3 p-8 text-muted-foreground">
            <p>{t('worldModel.atlas.startEditingSystem')}</p>
            <WorldModelHelp kind="system" empty />
          </div>
        )}
      </div>
    </div>
  )
}
