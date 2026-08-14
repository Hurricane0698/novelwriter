import { useMemo, useState } from 'react'
import { X, Box, Users, GitBranch, ExternalLink, BookOpenText } from 'lucide-react'
import { useUiLocale } from '@/contexts/UiLocaleContext'
import { cn } from '@/lib/utils'
import type { ContinueDebugSummary } from '@/types/api'
import {
  pickInitialInjectionSummaryCategory,
  type InjectionSummaryCategory,
} from '@/lib/injectionSummaryNavigation'

type Category = InjectionSummaryCategory

interface InjectionSummaryPanelProps {
  debug: ContinueDebugSummary
  onClose: () => void
  onOpenAtlas: (tab: Category) => void
  onWarmAtlas?: () => void
  onSelectItem?: (category: Category, label: string) => void
  activeCategory?: Category
  onActiveCategoryChange?: (category: Category) => void
}

export function InjectionSummaryPanel({
  debug,
  onClose,
  onOpenAtlas,
  onWarmAtlas,
  onSelectItem,
  activeCategory,
  onActiveCategoryChange,
}: InjectionSummaryPanelProps) {
  const { t } = useUiLocale()
  const [localCategory, setLocalCategory] = useState<Category>(() => pickInitialInjectionSummaryCategory(debug))
  const effectiveCategory = activeCategory ?? localCategory
  const categories: { key: Category; label: string; icon: typeof Box; tab: string }[] = useMemo(() => ([
    { key: 'entities', label: t('worldModel.common.entities'), icon: Users, tab: 'entities' },
    { key: 'relationships', label: t('worldModel.common.relationships'), icon: GitBranch, tab: 'relationships' },
    { key: 'systems', label: t('worldModel.common.systems'), icon: Box, tab: 'systems' },
  ]), [t])

  const itemsMap: Record<Category, string[]> = {
    systems: debug.injected_systems,
    entities: debug.injected_entities,
    relationships: debug.injected_relationships,
  }

  const currentItems = itemsMap[effectiveCategory]
  const worldCount = debug.injected_entities.length + debug.injected_systems.length + debug.injected_relationships.length
  const totalCount = worldCount + debug.injected_context_summaries.length

  return (
    <div className="flex h-full min-h-0 flex-col" data-testid="injection-summary-panel">
      {/* Header */}
      <div className="shrink-0 border-b border-[var(--nw-glass-border)] px-5 py-4">
        <div className="flex items-center justify-between">
          <div>
            <div className="text-[10px] font-semibold uppercase tracking-[0.26em] text-muted-foreground/72">
              Injection Summary
            </div>
            <div className="mt-1 text-sm font-medium text-foreground">
              {t('studio.injectionSummary.title', { count: totalCount })}
            </div>
          </div>
          <button
            type="button"
            onClick={onClose}
            className="inline-flex h-8 w-8 shrink-0 items-center justify-center rounded-lg text-muted-foreground hover:text-foreground hover:bg-[var(--nw-glass-bg-hover)] transition-colors"
          >
            <X size={14} />
          </button>
        </div>
      </div>

      {debug.injected_context_summaries.length > 0 ? (
        <div className="shrink-0 border-b border-[var(--nw-glass-border)] px-4 py-3">
          <div className="mb-2 flex items-center gap-2 text-[11px] font-medium text-foreground">
            <BookOpenText size={12} className="text-accent" />
            <span>{t('studio.injectionSummary.contextSummaries')}</span>
          </div>
          <div className="space-y-1">
            {debug.injected_context_summaries.map(item => (
              <div
                key={item}
                className="rounded-lg border border-[hsl(var(--accent)/0.2)] bg-[hsl(var(--accent)/0.06)] px-3 py-2 text-[12px] text-foreground/90"
              >
                {item}
              </div>
            ))}
          </div>
        </div>
      ) : null}

      {/* Category tabs */}
      <div className="shrink-0 flex gap-1.5 px-4 py-3 border-b border-[var(--nw-glass-border)]">
        {categories.map(({ key, label, icon: Icon }) => {
          const count = itemsMap[key].length
          const isActive = effectiveCategory === key
          return (
            <button
              key={key}
              type="button"
              onClick={() => {
                if (activeCategory === undefined) setLocalCategory(key)
                onActiveCategoryChange?.(key)
              }}
              className={cn(
                'flex items-center gap-1.5 rounded-lg px-2.5 py-1.5 text-[11px] font-medium transition-all',
                isActive
                  ? 'bg-[hsl(var(--accent)/0.15)] text-accent border border-[hsl(var(--accent)/0.3)]'
                  : 'text-muted-foreground hover:text-foreground hover:bg-[var(--nw-glass-bg-hover)] border border-transparent',
              )}
            >
              <Icon size={12} />
              <span>{label}</span>
              <span
                className={cn(
                  'rounded-full px-1.5 py-0.5 text-[9px] font-semibold leading-none',
                  isActive
                    ? 'bg-[hsl(var(--accent)/0.2)] text-accent'
                    : 'bg-[var(--nw-glass-bg)] text-muted-foreground',
                )}
              >
                {count}
              </span>
            </button>
          )
        })}
      </div>

      {/* Items list */}
      <div className="flex-1 min-h-0 overflow-y-auto nw-scrollbar-thin px-4 py-3">
        {currentItems.length === 0 ? (
          <div className="flex items-center justify-center py-8">
            <span className="text-xs text-muted-foreground">{t('studio.injectionSummary.empty')}</span>
          </div>
        ) : (
          <div className="flex flex-col gap-1">
            {currentItems.map((item, idx) => (
              <button
                key={idx}
                type="button"
                onClick={() => onSelectItem?.(effectiveCategory, item)}
                className={cn(
                  'w-full rounded-lg px-3 py-2 text-left transition-colors',
                  onSelectItem
                    ? 'hover:bg-[var(--nw-glass-bg-hover)]'
                    : '',
                )}
              >
                <div className="flex items-center gap-2.5">
                  <div
                    className={cn(
                      'w-1.5 h-1.5 rounded-full shrink-0',
                      effectiveCategory === 'entities' && 'bg-[hsl(var(--accent))]',
                      effectiveCategory === 'systems' && 'bg-[hsl(var(--color-status-confirmed))]',
                      effectiveCategory === 'relationships' && 'bg-[hsl(var(--color-vis-reference))]',
                    )}
                  />
                  <span className="text-[13px] text-foreground/90">
                    {item}
                  </span>
                </div>
              </button>
            ))}
          </div>
        )}
      </div>

      {/* Footer */}
      {worldCount > 0 && (
        <div className="shrink-0 border-t border-[var(--nw-glass-border)] px-4 py-3">
          <button
            type="button"
            onClick={() => onOpenAtlas(effectiveCategory)}
            onMouseEnter={onWarmAtlas}
            onFocus={onWarmAtlas}
            className="flex w-full items-center justify-center gap-2 rounded-lg px-3 py-2.5 text-[12px] text-muted-foreground hover:text-accent hover:bg-[var(--nw-glass-bg-hover)] transition-colors"
          >
            <ExternalLink size={12} />
            <span>{t('studio.injectionSummary.openInAtlas')}</span>
          </button>
        </div>
      )}
    </div>
  )
}
