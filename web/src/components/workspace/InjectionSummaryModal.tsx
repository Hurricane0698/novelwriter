import { useState, useEffect } from 'react'
import { useNavigate, useLocation } from 'react-router-dom'
import { X, Box, Users, GitBranch } from 'lucide-react'
import { cn } from '@/lib/utils'
import type { ContinueDebugSummary } from '@/types/api'

type Category = 'systems' | 'entities' | 'relationships'

const categories: { key: Category; label: string; icon: typeof Box; tab: string }[] = [
  { key: 'systems', label: '体系', icon: Box, tab: 'systems' },
  { key: 'entities', label: '实体', icon: Users, tab: 'entities' },
  { key: 'relationships', label: '关系', icon: GitBranch, tab: 'relationships' },
]

function pickInitialCategory(debug: ContinueDebugSummary): Category {
  if (debug.injected_entities.length > 0) return 'entities'
  if (debug.injected_systems.length > 0) return 'systems'
  if (debug.injected_relationships.length > 0) return 'relationships'
  return 'entities'
}

interface InjectionSummaryModalProps {
  onClose: () => void
  debug: ContinueDebugSummary
  novelId: string
}

export function InjectionSummaryModal({ onClose, debug, novelId }: InjectionSummaryModalProps) {
  const navigate = useNavigate()
  const location = useLocation()
  const [activeCategory, setActiveCategory] = useState<Category>(() => pickInitialCategory(debug))

  useEffect(() => {
    const handler = (e: KeyboardEvent) => {
      if (e.key === 'Escape') onClose()
    }
    document.addEventListener('keydown', handler)
    return () => document.removeEventListener('keydown', handler)
  }, [onClose])

  const itemsMap: Record<Category, string[]> = {
    systems: debug.injected_systems,
    entities: debug.injected_entities,
    relationships: debug.injected_relationships,
  }

  const currentItems = itemsMap[activeCategory]

  const handleItemClick = (category: Category) => {
    const tab = categories.find(c => c.key === category)?.tab ?? 'entities'
    // Only encode returnTo when results are persisted in URL (continuations param exists).
    // If streaming failed, there's nothing recoverable to return to.
    const hasPersistedResults = new URLSearchParams(location.search).has('continuations')
    const returnSuffix = hasPersistedResults
      ? `&returnTo=${encodeURIComponent(location.pathname + location.search)}`
      : ''
    navigate(`/world/${novelId}?tab=${tab}${returnSuffix}`)
  }

  return (
    <>
      {/* Backdrop */}
      <div
        className="fixed inset-0 z-50 bg-[var(--nw-backdrop)] animate-in fade-in duration-150"
        onClick={onClose}
      />

      {/* Modal */}
      <div className="fixed inset-0 z-50 flex items-center justify-center pointer-events-none">
        <div
          className={cn(
            'pointer-events-auto',
            'w-[520px] max-w-[90vw] max-h-[70vh]',
            'rounded-2xl border border-[var(--nw-glass-border-hover)]',
            'bg-[hsl(var(--nw-modal-bg))] backdrop-blur-[24px]',
            'shadow-[0_24px_80px_var(--nw-backdrop)]',
            'flex flex-col text-foreground',
          )}
          onClick={(e) => e.stopPropagation()}
        >
          {/* Header */}
          <div className="flex items-center justify-between px-6 pt-5 pb-3">
            <h3 className="text-sm font-semibold text-foreground">注入摘要</h3>
            <button
              type="button"
              onClick={onClose}
              className="rounded-lg p-1.5 text-muted-foreground hover:text-foreground hover:bg-[var(--nw-glass-bg-hover)] transition-colors"
            >
              <X size={16} />
            </button>
          </div>

          {/* Category tabs */}
          <div className="flex gap-1.5 px-6 pb-4">
            {categories.map(({ key, label, icon: Icon }) => {
              const count = itemsMap[key].length
              const isActive = activeCategory === key
              return (
                <button
                  key={key}
                  type="button"
                  onClick={() => setActiveCategory(key)}
                  className={cn(
                    'flex items-center gap-2 rounded-lg px-3.5 py-2 text-xs font-medium transition-all',
                    isActive
                      ? 'bg-[hsl(var(--accent)/0.15)] text-accent border border-[hsl(var(--accent)/0.3)]'
                      : 'text-muted-foreground hover:text-foreground hover:bg-[var(--nw-glass-bg-hover)] border border-transparent',
                  )}
                >
                  <Icon size={13} />
                  <span>{label}</span>
                  <span
                    className={cn(
                      'rounded-full px-1.5 py-0.5 text-[10px] font-semibold leading-none',
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

          {/* Divider */}
          <div className="h-px bg-[var(--nw-glass-border)] mx-6" />

          {/* Items list */}
          <div className="flex-1 min-h-0 overflow-y-auto nw-scrollbar-thin px-6 py-4">
            {currentItems.length === 0 ? (
              <div className="flex items-center justify-center py-10">
                <span className="text-xs text-muted-foreground">无注入内容</span>
              </div>
            ) : (
              <div className="flex flex-col gap-1.5">
                {currentItems.map((item, idx) => (
                  <button
                    key={idx}
                    type="button"
                    onClick={() => handleItemClick(activeCategory)}
                    className={cn(
                      'text-left rounded-lg px-3.5 py-2.5',
                      'border border-transparent',
                      'hover:bg-[var(--nw-glass-bg-hover)] hover:border-[var(--nw-glass-border)]',
                      'transition-all group',
                    )}
                  >
                    <div className="flex items-center gap-3">
                      <div
                        className={cn(
                          'w-1.5 h-1.5 rounded-full shrink-0',
                          activeCategory === 'entities' && 'bg-[hsl(var(--accent))]',
                          activeCategory === 'systems' && 'bg-[hsl(var(--color-status-confirmed))]',
                          activeCategory === 'relationships' && 'bg-[hsl(var(--color-vis-reference))]',
                        )}
                      />
                      <span className="text-sm text-foreground/90 group-hover:text-foreground transition-colors">
                        {item}
                      </span>
                    </div>
                  </button>
                ))}
              </div>
            )}
          </div>

          {/* Footer hint */}
          {currentItems.length > 0 && (
            <>
              <div className="h-px bg-[var(--nw-glass-border)] mx-6" />
              <div className="px-6 py-3 flex items-center justify-center">
                <button
                  type="button"
                  onClick={() => handleItemClick(activeCategory)}
                  className="text-[11px] text-muted-foreground hover:text-accent transition-colors"
                >
                  在世界模型中查看全部 →
                </button>
              </div>
            </>
          )}
        </div>
      </div>
    </>
  )
}
