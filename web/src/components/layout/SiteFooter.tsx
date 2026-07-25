import { Link } from 'react-router-dom'
import { useUiLocale } from '@/contexts/UiLocaleContext'
import { cn } from '@/lib/utils'

type SiteFooterProps = {
  compact?: boolean
  className?: string
}

export function SiteFooter({ compact, className }: SiteFooterProps) {
  const { t } = useUiLocale()
  const links = [
    { to: '/terms', label: t('footer.link.terms') },
    { to: '/privacy', label: t('footer.link.privacy') },
    { to: '/copyright', label: t('footer.link.copyright') },
  ]

  return (
    <footer
      className={cn(
        'border-t border-[var(--nw-glass-border)] bg-[hsl(var(--background)/0.45)] backdrop-blur-xl',
        compact ? 'mt-8' : 'mt-20',
        className,
      )}
    >
      <div
        className={cn(
          'mx-auto flex w-full max-w-6xl flex-col gap-5 px-6',
          compact ? 'py-6 md:flex-row md:items-center md:justify-between' : 'py-8 md:flex-row md:items-center md:justify-between md:px-12',
        )}
      >
        <div className="flex flex-col gap-1">
          <div className="font-mono text-base font-bold text-foreground">NovWr</div>
          <p className="max-w-[34rem] text-sm leading-6 text-muted-foreground">
            {t('footer.description')}
          </p>
        </div>

        <nav className="flex flex-wrap items-center gap-x-5 gap-y-2 text-sm text-muted-foreground">
          {links.map((link) => (
            <Link
              key={link.to}
              to={link.to}
              className="transition-colors hover:text-foreground"
            >
              {link.label}
            </Link>
          ))}
        </nav>
      </div>
    </footer>
  )
}
