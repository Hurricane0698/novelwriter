import { BookOpen, Plus } from 'lucide-react'
import { GlassCard } from '@/components/GlassCard'
import { NwButton } from '@/components/ui/nw-button'

export function EmptyState({
  onCreate,
  disabled,
}: {
  onCreate: () => void
  disabled?: boolean
}) {
  return (
    <GlassCard className="flex-1 p-8 flex flex-col items-center justify-center gap-5 text-center">
      <BookOpen size={48} className="text-muted-foreground" />
      <p className="m-0 text-[15px] text-muted-foreground">
        还没有作品，开始创作你的第一部小说吧
      </p>
      <NwButton
        onClick={onCreate}
        disabled={disabled}
        variant="accent"
        className="rounded-full px-6 py-2.5 text-sm font-semibold shadow-[0_0_24px_hsl(var(--accent)/0.35)]"
      >
        <Plus size={18} />
        新建作品
      </NwButton>
    </GlassCard>
  )
}
