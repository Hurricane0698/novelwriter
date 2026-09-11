import { Link, useLocation } from 'react-router-dom'
import { useUiLocale } from '@/contexts/UiLocaleContext'
import { isHostedRuntime } from '@/lib/runtimeMode'
import { cn } from '@/lib/utils'

type SiteFooterProps = {
  compact?: boolean
  className?: string
}

export function SiteFooter({ compact, className }: SiteFooterProps) {
  const { t } = useUiLocale()
  const { pathname } = useLocation()
  const isLanding = pathname === '/'
  // Legal pages cover the official hosted entry only; local runtimes keep a clean footer.
  const links = isHostedRuntime()
    ? [
        { to: '/terms', label: t('footer.link.terms') },
        { to: '/privacy', label: t('footer.link.privacy') },
        { to: '/copyright', label: t('footer.link.copyright') },
      ]
    : []

  return (
    <footer
      className={cn(
        isLanding
          ? 'border-t border-[hsl(var(--lp-ink)/0.12)] bg-[hsl(var(--lp-paper))]'
          : 'border-t border-[var(--nw-glass-border)] bg-[hsl(var(--background)/0.45)] backdrop-blur-xl',
        isLanding ? 'mt-0' : compact ? 'mt-8' : 'mt-20',
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
          <div className={cn('font-mono text-base font-bold', isLanding ? 'text-[hsl(var(--lp-ink))]' : 'text-foreground')}>
            NovWr
          </div>
          <p
            className={cn(
              'max-w-[34rem] text-sm leading-6',
              isLanding ? 'text-[hsl(var(--lp-ink)/0.6)]' : 'text-muted-foreground',
            )}
          >
            {t('footer.description')}
          </p>
        </div>

        {links.length > 0 ? (
          <nav
            className={cn(
              'flex flex-wrap items-center gap-x-5 gap-y-2 text-sm',
              isLanding ? 'text-[hsl(var(--lp-ink)/0.6)]' : 'text-muted-foreground',
            )}
          >
            {links.map((link) => (
              <Link
                key={link.to}
                to={link.to}
                className={cn(
                  'transition-colors',
                  isLanding ? 'hover:text-[hsl(var(--lp-ink))]' : 'hover:text-foreground',
                )}
              >
                {link.label}
              </Link>
            ))}
          </nav>
        ) : null}
      </div>
    </footer>
  )
}
