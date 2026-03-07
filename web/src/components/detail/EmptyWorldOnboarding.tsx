import { Sparkles, BookOpen } from 'lucide-react'
import { cn } from '@/lib/utils'
import { GlassSurface } from '@/components/ui/glass-surface'

export function EmptyWorldOnboarding({
  className,
  onGenerate,
  onBootstrap,
  onDismiss,
  bootstrapPending,
  bootstrapError,
}: {
  className?: string
  onGenerate: () => void
  onBootstrap: () => void
  onDismiss: () => void
  bootstrapPending?: boolean
  bootstrapError?: string | null
}) {
  return (
    <div className={cn('flex flex-1 items-center justify-center px-8 py-10', className)} data-testid="world-onboarding">
      <div className="w-full max-w-4xl space-y-6">
        <div className="space-y-2">
          <div className="text-2xl font-light text-foreground tracking-tight">
            先构建世界观，再开始写作
          </div>
          <div className="text-sm text-muted-foreground">
            你可以从设定文本生成草稿，或从章节中自动提取实体与关系。
          </div>
        </div>

        <div className="grid grid-cols-1 md:grid-cols-2 gap-5">
          <GlassSurface
            asChild
            variant="container"
            hoverable
            className="rounded-2xl p-6 text-left focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent"
          >
            <button
              type="button"
              onClick={onGenerate}
              data-testid="world-onboarding-generate"
            >
              <div className="flex items-start gap-4">
                <div className="h-10 w-10 rounded-xl bg-[hsl(var(--color-accent)/0.18)] border border-[hsl(var(--color-accent)/0.28)] flex items-center justify-center text-[hsl(var(--color-accent))]">
                  <Sparkles className="h-5 w-5" />
                </div>
                <div className="flex-1 space-y-1">
                  <div className="text-base font-semibold text-foreground">从设定生成</div>
                  <div className="text-sm text-muted-foreground">
                    粘贴世界观设定，让 AI 提取实体、关系与体系草稿，然后你再逐条确认。
                  </div>
                </div>
              </div>
            </button>
          </GlassSurface>

          <GlassSurface
            asChild
            variant="container"
            hoverable
            className="rounded-2xl p-6 text-left focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent"
          >
            <button
              type="button"
              onClick={onBootstrap}
              disabled={bootstrapPending}
              data-testid="world-onboarding-bootstrap"
            >
              <div className="flex items-start gap-4">
                <div className="h-10 w-10 rounded-xl bg-[hsl(var(--foreground)/0.08)] border border-[var(--nw-glass-border)] flex items-center justify-center text-foreground/80">
                  <BookOpen className="h-5 w-5" />
                </div>
                <div className="flex-1 space-y-1">
                  <div className="text-base font-semibold text-foreground">从章节提取</div>
                  <div className="text-sm text-muted-foreground">
                    从已上传的章节内容中自动提取实体与关系草稿。
                  </div>
                  {bootstrapPending ? (
                    <div className="text-xs text-muted-foreground pt-1">处理中...</div>
                  ) : null}
                </div>
              </div>
            </button>
          </GlassSurface>
        </div>

        {bootstrapError ? (
          <div className="rounded-xl border border-[hsl(var(--color-warning)/0.35)] bg-[hsl(var(--color-warning)/0.08)] px-4 py-3 text-sm text-[hsl(var(--color-warning))] whitespace-pre-wrap">
            {bootstrapError}
          </div>
        ) : null}

        <div className="pt-1">
          <button
            type="button"
            className="text-sm text-muted-foreground hover:text-foreground underline underline-offset-4"
            onClick={onDismiss}
            data-testid="world-onboarding-dismiss"
          >
            前往世界模型页稍后添加 →
          </button>
        </div>
      </div>
    </div>
  )
}
