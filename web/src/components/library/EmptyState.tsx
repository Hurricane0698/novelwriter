import { BookOpen } from 'lucide-react'
import { GlassCard } from '@/components/GlassCard'
import { useUiLocale } from '@/contexts/UiLocaleContext'

export function EmptyState() {
  const { t } = useUiLocale()

  return (
    <GlassCard className="flex-1 p-8 flex flex-col items-center justify-center gap-5 text-center">
      <BookOpen size={48} className="text-muted-foreground" />
      <p className="m-0 text-[15px] text-muted-foreground">
        {t('library.empty.title')}
      </p>
    </GlassCard>
  )
}
