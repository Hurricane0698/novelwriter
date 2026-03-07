import { useState } from 'react'
import { Sparkles, ChevronRight } from 'lucide-react'
import { cn } from '@/lib/utils'
import { BootstrapPanel } from '@/components/world-model/shared/BootstrapPanel'
import { WorldGenerationDialog } from '@/components/world-model/shared/WorldGenerationDialog'

function ActionRow({
  icon: Icon,
  label,
  onClick,
  disabled,
  testId,
}: {
  icon: React.ComponentType<{ className?: string }>
  label: string
  onClick: () => void
  disabled?: boolean
  testId?: string
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      disabled={disabled}
      className={cn(
        'flex w-full items-center gap-3 rounded-lg px-3 py-2.5 text-left text-xs',
        'text-muted-foreground transition-colors',
        'hover:bg-[var(--nw-glass-bg-hover)] hover:text-foreground',
        'disabled:opacity-50 disabled:pointer-events-none',
      )}
      data-testid={testId}
    >
      <Icon className="h-4 w-4 shrink-0 opacity-70" />
      <span className="flex-1">{label}</span>
      <ChevronRight className="h-3.5 w-3.5 shrink-0 opacity-40" />
    </button>
  )
}

export function WorldBuildSection({
  novelId,
  className,
}: {
  novelId: number
  className?: string
}) {
  const [genOpen, setGenOpen] = useState(false)

  return (
    <div className={cn('space-y-2', className)} data-testid="world-build-section">
      <div className="text-[11px] font-medium tracking-wide text-muted-foreground/70 uppercase">
        构建世界观
      </div>

      <div className="rounded-xl border border-[var(--nw-glass-border)] bg-[var(--nw-glass-bg)] divide-y divide-[var(--nw-glass-border)]">
        <ActionRow
          icon={Sparkles}
          label="从设定文本生成"
          onClick={() => setGenOpen(true)}
          testId="world-build-generate"
        />
        <BootstrapPanel novelId={novelId} variant="sidebar" />
      </div>

      <WorldGenerationDialog novelId={novelId} open={genOpen} onOpenChange={setGenOpen} />
    </div>
  )
}
