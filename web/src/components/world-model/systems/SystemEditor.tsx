import { useState, type ReactNode } from 'react'
import { WorldModelHelp } from '@/components/world-model/shared/WorldModelHelp'
import { WorldSourceRefs } from '@/components/world-model/shared/WorldSourceRefs'
import '@/lib/uiMessagePacks/novel'
import { InlineEdit } from '@/components/world-model/shared/InlineEdit'
import { VisibilityDot } from '@/components/world-model/shared/VisibilityDot'
import { ConstraintsPanel } from '@/components/world-model/systems/ConstraintsPanel'
import { HierarchyEditor } from '@/components/world-model/systems/HierarchyEditor'
import { LegacyGraphReadonly } from '@/components/world-model/systems/LegacyGraphReadonly'
import { TimelineEditor } from '@/components/world-model/systems/TimelineEditor'
import { ListEditor } from '@/components/world-model/systems/ListEditor'
import { useUpdateSystem, useDeleteSystem } from '@/hooks/world/useSystems'
import { isLegacyGraphDisplayType } from '@/lib/worldSystemDisplay'
import { useUiLocale } from '@/contexts/UiLocaleContext'
import type { WorldSystem } from '@/types/api'

type HierarchyEditorData = Parameters<typeof HierarchyEditor>[0]['data']
type TimelineEditorData = Parameters<typeof TimelineEditor>[0]['data']
type ListEditorData = Parameters<typeof ListEditor>[0]['data']

export function SystemEditor({ novelId, system, onBack }: {
  novelId: number
  system: WorldSystem
  onBack: () => void
}) {
  const { t } = useUiLocale()
  const updateSystem = useUpdateSystem(novelId)
  const deleteSystem = useDeleteSystem(novelId)
  const [confirmDelete, setConfirmDelete] = useState(false)

  const save = (patch: Record<string, unknown>) => {
    updateSystem.mutate({ systemId: system.id, data: patch })
  }

  const saveData = <T extends object>(data: T) => {
    save({ data: data as unknown as Record<string, unknown> })
  }
  const isLegacyGraph = isLegacyGraphDisplayType(system.display_type)
  let editorContent: ReactNode
  if (isLegacyGraph) {
    editorContent = <LegacyGraphReadonly data={system.data} />
  } else if (system.display_type === 'hierarchy') {
    editorContent = <HierarchyEditor data={system.data as unknown as HierarchyEditorData} onUpdate={saveData} />
  } else if (system.display_type === 'timeline') {
    editorContent = <TimelineEditor data={system.data as unknown as TimelineEditorData} onUpdate={saveData} />
  } else if (system.display_type === 'list') {
    editorContent = <ListEditor data={system.data as unknown as ListEditorData} onUpdate={saveData} />
  } else {
    editorContent = (
      <div className="rounded-2xl border border-[var(--nw-glass-border)] bg-[var(--nw-glass-bg)] px-4 py-3 text-sm text-muted-foreground">
        {t('worldModel.system.unsupportedType')}
      </div>
    )
  }

  return (
    <div className="max-w-5xl mx-auto px-8 py-8 space-y-4" data-testid="system-editor">
      <button className="text-sm text-muted-foreground hover:text-foreground" onClick={onBack}>
        {t('worldModel.system.back')}
      </button>
      <WorldModelHelp kind="system" />
      <WorldSourceRefs novelId={novelId} sources={system.source_refs} />
      <div className="rounded-2xl border border-[var(--nw-glass-border)] bg-[var(--nw-glass-bg)] backdrop-blur-2xl p-4 space-y-4">
        <div className="flex items-center gap-3">
          <InlineEdit
            value={system.name}
            onSave={v => save({ name: v })}
            className="text-lg font-semibold"
            placeholder={t('worldModel.system.namePlaceholder')}
          />
          <VisibilityDot
            visibility={system.visibility}
            onChange={v => save({ visibility: v })}
          />
          <button
            className={`text-xs ml-auto ${confirmDelete ? 'text-[hsl(var(--color-danger))]' : 'text-muted-foreground hover:text-[hsl(var(--color-danger))]'}`}
            onClick={() => {
              if (confirmDelete) {
                deleteSystem.mutate(system.id, { onSuccess: onBack })
              } else {
                setConfirmDelete(true)
              }
            }}
            onMouseLeave={() => setConfirmDelete(false)}
          >{confirmDelete ? t('worldModel.system.deleteConfirm') : t('worldModel.system.delete')}</button>
        </div>
        {editorContent}
        <ConstraintsPanel
          constraints={system.constraints}
          onChange={constraints => save({ constraints })}
        />
      </div>
    </div>
  )
}
