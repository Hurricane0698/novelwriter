import { AlertTriangle, ArrowUpRight, Clock3, Sparkles } from 'lucide-react'
import { cn } from '@/lib/utils'

export type AtlasAssistAttentionBannerTone = 'running' | 'needs_review' | 'failed'

export function AtlasAssistAttentionBanner({ tone, title, description, actionLabel, onAction }: {
  tone: AtlasAssistAttentionBannerTone
  title: string
  description: string
  actionLabel?: string
  onAction?: () => void
}) {
  const Icon = tone === 'failed' ? AlertTriangle : tone === 'running' ? Clock3 : Sparkles
  return (
    <section className={cn('mb-3 rounded-xl border p-3.5', tone === 'failed'
      ? 'border-[hsl(var(--color-warning)/0.3)] bg-[hsl(var(--color-warning)/0.06)]'
      : 'border-[var(--nw-copilot-border)] bg-foreground/[0.03]')}
      data-testid="atlas-assist-attention-banner" data-tone={tone}>
      <div className="flex items-start gap-2.5">
        <Icon className="mt-0.5 h-4 w-4 shrink-0 text-muted-foreground" />
        <div className="min-w-0">
          <h3 className="text-sm font-medium">{title}</h3>
          <p className="mt-1 text-xs leading-5 text-muted-foreground">{description}</p>
          {actionLabel && onAction && <button type="button" onClick={onAction}
            className="mt-3 inline-flex items-center gap-1.5 rounded-lg bg-foreground px-3 py-1.5 text-xs font-medium text-background hover:bg-foreground/85"
            data-testid="atlas-assist-attention-action">
            {actionLabel}<ArrowUpRight className="h-3.5 w-3.5" />
          </button>}
        </div>
      </div>
    </section>
  )
}
