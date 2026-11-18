import { type KeyboardEvent } from 'react'
import { WorldModelHelp } from '@/components/world-model/shared/WorldModelHelp'
import { WorldSourceRefs } from '@/components/world-model/shared/WorldSourceRefs'
import { ArrowLeft, Compass } from 'lucide-react'
import { AssistToggleButton } from '@/components/studio/AssistToggleButton'
import { LABELS } from '@/constants/labels'
import { useUiLocale } from '@/contexts/UiLocaleContext'
import { InlineEdit } from '@/components/world-model/shared/InlineEdit'
import { VisibilityDot } from '@/components/world-model/shared/VisibilityDot'
import { NwButton } from '@/components/ui/nw-button'
import { useConfirmSystems, useUpdateSystem, useWorldSystem, useWorldSystems } from '@/hooks/world/useSystems'
import type { UiMessageKey, UiMessageParams } from '@/lib/uiMessages'
import { getSystemDisplayTypeLabel, isLegacyGraphDisplayType } from '@/lib/worldSystemDisplay'
import { cn } from '@/lib/utils'
import type { WorldSystem } from '@/types/api'

function getSystemStructureSummary(system: WorldSystem, t: (key: UiMessageKey, params?: UiMessageParams) => string) {
  if (isLegacyGraphDisplayType(system.display_type)) {
    return t('studio.stage.system.summary.legacyGraph')
  }

  if (system.display_type === 'hierarchy') {
    const nodes = Array.isArray((system.data as { nodes?: unknown[] }).nodes)
      ? (system.data as { nodes: unknown[] }).nodes.length
      : 0
    return t('studio.stage.system.summary.hierarchy', { count: nodes })
  }

  if (system.display_type === 'timeline') {
    const events = Array.isArray((system.data as { events?: unknown[] }).events)
      ? (system.data as { events: unknown[] }).events.length
      : 0
    return t('studio.stage.system.summary.timeline', { count: events })
  }

  const items = Array.isArray((system.data as { items?: unknown[] }).items)
    ? (system.data as { items: unknown[] }).items.length
    : 0
  return t('studio.stage.system.summary.list', { count: items })
}

export function StudioSystemStage({
  novelId,
  systemId,
  onSelectSystem,
  onOpenAtlas,
  onWarmAtlas,
  onReturnToArtifact,
  assistOpen,
  onToggleAssist,
}: {
  novelId: number
  systemId: number | null
  onSelectSystem: (systemId: number) => void
  onOpenAtlas: () => void
  onWarmAtlas?: () => void
  onReturnToArtifact?: () => void
  assistOpen?: boolean
  onToggleAssist?: () => void
}) {
  const { t } = useUiLocale()
  const { data: systems = [] } = useWorldSystems(novelId)
  const { data: system } = useWorldSystem(novelId, systemId)
  const updateSystem = useUpdateSystem(novelId)
  const confirmSystems = useConfirmSystems(novelId)

  return (
    <div className="flex-1 min-h-0 flex flex-col overflow-hidden" data-testid="studio-system-stage">
      <div className="shrink-0 border-b border-[var(--nw-glass-border)] px-6 py-4">
        <div className="flex flex-col gap-3 lg:flex-row lg:items-start lg:justify-between">
          <div className="space-y-1">
            <div className="text-[11px] font-semibold uppercase tracking-[0.24em] text-muted-foreground">
              Studio
            </div>
            <h2 className="text-lg font-semibold text-foreground">
              {t('studio.stage.system.title')}
            </h2>
            <WorldModelHelp kind="system" />
            {system && <WorldSourceRefs novelId={novelId} sources={system.source_refs} />}
          </div>

          <div className="flex flex-wrap gap-2">
            {onReturnToArtifact ? (
              <NwButton
                onClick={onReturnToArtifact}
                variant="glass"
                className="rounded-[10px] px-4 py-2 text-sm font-medium"
              >
                <ArrowLeft size={14} />
                {t('studio.stage.returnToResults')}
              </NwButton>
            ) : null}
            <NwButton
              onClick={onOpenAtlas}
              onMouseEnter={onWarmAtlas}
              onFocus={onWarmAtlas}
              variant="accentOutline"
              className="rounded-[10px] px-4 py-2 text-sm font-medium"
            >
              <Compass size={14} />
              {t('studio.stage.openInAtlas')}
            </NwButton>
            {onToggleAssist ? <AssistToggleButton active={assistOpen} onClick={onToggleAssist} /> : null}
          </div>
        </div>
      </div>

      <div className="flex-1 min-h-0 flex overflow-hidden">
        <div className="w-[280px] shrink-0 border-r border-[var(--nw-glass-border)] bg-[var(--nw-glass-bg)] backdrop-blur-2xl overflow-hidden flex flex-col min-h-0">
          <div className="shrink-0 p-4 space-y-2">
            <div className="text-sm font-medium text-foreground">{t('studio.stage.system.sidebarTitle')}</div>
            <div className="text-xs text-muted-foreground">
              {t('studio.stage.system.count', { count: systems.length })}
            </div>
          </div>

          <div className="nw-scrollbar-thin min-h-0 flex-1 overflow-y-auto">
            {systems.length === 0 ? (
              <div className="px-4 py-2 text-sm text-muted-foreground">
                {t('studio.stage.system.empty')}
              </div>
            ) : (
              systems.map((candidate) => {
                const selected = candidate.id === systemId
                return (
                  <div
                    key={candidate.id}
                    className={cn(
                      'w-full px-4 py-2 text-left text-sm flex items-center gap-2 transition-colors cursor-pointer',
                      selected
                        ? 'bg-[var(--nw-glass-bg-hover)] border-l-2 border-l-accent'
                        : 'hover:bg-[var(--nw-glass-bg-hover)]',
                    )}
                    role="button"
                    tabIndex={0}
                    onClick={() => onSelectSystem(candidate.id)}
                    onKeyDown={(e: KeyboardEvent<HTMLDivElement>) => {
                      if (e.key === 'Enter' || e.key === ' ') {
                        e.preventDefault()
                        onSelectSystem(candidate.id)
                      }
                    }}
                  >
                    {candidate.status === 'draft' && (
                      <span className="w-1.5 h-1.5 rounded-full bg-[hsl(var(--color-status-draft))] shrink-0" />
                    )}
                    <span className="truncate flex-1 text-foreground">
                      {candidate.name || t('studio.stage.system.unnamed')}
                    </span>
                    <span className="text-xs text-muted-foreground shrink-0">
                      {getSystemDisplayTypeLabel(candidate.display_type)}
                    </span>
                  </div>
                )
              })
            )}
          </div>
        </div>

        <div className="flex-1 min-w-0 overflow-y-auto">
          {!systemId || !system ? (
            <div className="flex h-full items-center justify-center text-sm text-muted-foreground">
              {t('studio.stage.system.selectPrompt')}
            </div>
          ) : (
            <div className="mx-auto flex max-w-5xl flex-col gap-4 px-8 py-8">
              <div className="rounded-2xl border border-[var(--nw-glass-border)] bg-[var(--nw-glass-bg)] backdrop-blur-2xl p-5 space-y-4">
                <div className="flex flex-wrap items-start gap-3">
                  <div className="flex-1 min-w-[240px] space-y-2">
                    <div className="flex flex-wrap items-center gap-3">
                      <InlineEdit
                        value={system.name}
                        onSave={(value) => updateSystem.mutate({ systemId: system.id, data: { name: value } })}
                        className="text-xl font-semibold text-foreground"
                        placeholder={LABELS.PH_SYSTEM_NAME}
                      />
                      <VisibilityDot
                        visibility={system.visibility}
                        onChange={(visibility) => updateSystem.mutate({ systemId: system.id, data: { visibility } })}
                      />
                      <span className="rounded-full border border-[var(--nw-glass-border)] bg-[var(--nw-glass-bg)] px-2 py-0.5 text-xs text-muted-foreground">
                        {getSystemDisplayTypeLabel(system.display_type)}
                      </span>
                      <span
                        className={cn(
                          'text-xs',
                          system.status === 'draft'
                            ? 'text-[hsl(var(--color-status-draft))]'
                            : 'text-[hsl(var(--color-status-confirmed))]',
                        )}
                      >
                        {system.status === 'draft' ? `● ${t('worldModel.common.statusDraft')}` : `✓ ${t('worldModel.common.statusConfirmed')}`}
                      </span>
                    </div>

                    <div className="text-sm text-muted-foreground">
                      {getSystemStructureSummary(system, t)}
                    </div>
                  </div>

                  {system.status === 'draft' ? (
                    <NwButton
                      onClick={() => confirmSystems.mutate([system.id])}
                      variant="accentOutline"
                      className="rounded-[10px] px-4 py-2 text-sm font-medium"
                    >
                      {t('studio.stage.system.confirm')}
                    </NwButton>
                  ) : null}
                </div>

                <div className="rounded-xl border border-[var(--nw-glass-border)] bg-[hsl(var(--background)/0.28)] px-4 py-3 text-xs text-muted-foreground">
                  {t('studio.stage.system.help')}
                </div>
              </div>

              <div className="rounded-2xl border border-[var(--nw-glass-border)] bg-[var(--nw-glass-bg)] backdrop-blur-2xl p-5">
                <div className="mb-2 text-xs font-semibold tracking-wider text-muted-foreground">
                  {t('studio.stage.system.descriptionSection')}
                </div>
                <InlineEdit
                  value={system.description}
                  onSave={(value) => updateSystem.mutate({ systemId: system.id, data: { description: value } })}
                  multiline
                  variant="transparent"
                  className="text-sm text-foreground"
                  placeholder={t('worldModel.common.description')}
                />
              </div>
            </div>
          )}
        </div>
      </div>
    </div>
  )
}
