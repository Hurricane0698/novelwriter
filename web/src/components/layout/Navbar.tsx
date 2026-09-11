import { type ReactNode } from "react"
import { Link, useLocation } from "react-router-dom"
import { useAuth } from "@/contexts/AuthContext"
import { useUiLocale } from "@/contexts/UiLocaleContext"
import { Avatar, AvatarFallback } from "@/components/ui/avatar"
import { cn } from "@/lib/utils"
import { NwButton } from "@/components/ui/nw-button"
import { isHostedRuntime } from "@/lib/runtimeMode"

export type NavbarProps = {
    compact?: boolean
    leftContent?: ReactNode
    rightContent?: ReactNode
    hideLinks?: boolean
    /** Defaults to `fixed`. Use `static` for pages that manage their own scroll containers. */
    position?: "fixed" | "static"
}

export function Navbar({
    compact,
    leftContent,
    rightContent,
    hideLinks,
    position = "fixed",
}: NavbarProps) {
    const { isLoggedIn, user } = useAuth()
    const { t } = useUiLocale()
    const { pathname } = useLocation()
    const isLanding = pathname === "/"
    const isHosted = isHostedRuntime()

    const navPositionClass =
        position === "fixed" ? "fixed inset-x-0 top-0 z-50" : "w-full"
    const heightClass = compact ? "h-14" : "h-16"
    const paddingClass = isLanding ? "max-w-[1376px] px-6 sm:px-8 lg:px-12" : compact ? "px-6" : "px-12"
    const brandSizeClass = compact ? "text-lg" : "text-xl"

    return (
        <nav
            className={cn(
                navPositionClass,
                heightClass,
                isLanding
                    ? "border-b border-[hsl(var(--lp-ink)/0.08)] bg-[hsl(var(--lp-paper))]"
                    : "border-b border-[var(--nw-glass-border)] bg-[hsl(var(--background)/0.60)] backdrop-blur-xl",
            )}
        >
            <div className={`mx-auto h-full flex items-center justify-between ${paddingClass}`}>
                {leftContent ?? (
                    <div className="flex items-center gap-6">
                        <Link to="/" className={`font-mono ${brandSizeClass} font-bold ${isLanding ? 'text-[hsl(var(--lp-ink))] hover:opacity-70' : 'text-foreground hover:opacity-80'} transition-opacity`}>
                            NovWr
                        </Link>
                        {!hideLinks ? (
                            <div className={`hidden md:flex items-center gap-6 text-sm font-medium ${isLanding ? 'text-[hsl(var(--lp-ink)/0.6)]' : 'text-muted-foreground'}`}>
                                {isLanding ? (
                                    <>
                                        <a href="#narrative" className={`${isLanding ? 'hover:text-[hsl(var(--lp-ink))]' : 'hover:text-foreground'} transition-colors`}>{t('navbar.features')}</a>
                                        {isHosted ? (
                                            <a
                                                href="https://github.com/Hurricane0698/novelwriter#readme"
                                                target="_blank"
                                                rel="noreferrer"
                                                className="hover:text-[hsl(var(--lp-ink))] transition-colors"
                                            >
                                                {t('navbar.docs')}
                                            </a>
                                        ) : null}
                                    </>
                                ) : (
                                    <>
                                        <Link
                                            to="/library"
                                            className="hover:text-foreground transition-colors"
                                        >
                                            {t('navbar.library')}
                                        </Link>
                                        <Link
                                            to="/settings"
                                            className="hover:text-foreground transition-colors"
                                        >
                                            {t('navbar.settings')}
                                        </Link>
                                    </>
                                )}
                            </div>
                        ) : null}
                    </div>
                )}
                {rightContent ?? (
                    <div className="flex items-center gap-4">
                        {isHosted ? (isLoggedIn && user ? (
                            <Link to="/settings">
                                <Avatar className="h-8 w-8 transition-opacity hover:opacity-80">
                                    <AvatarFallback>{user.username[0]?.toUpperCase()}</AvatarFallback>
                                </Avatar>
                            </Link>
                        ) : (
                            isLanding ? (
                                <NwButton
                                    asChild
                                    className="lp-cta-primary hidden md:inline-flex h-9 rounded-full px-5 text-sm font-medium shadow-none"
                                >
                                    <Link to="/login">{t('navbar.login')}</Link>
                                </NwButton>
                            ) : (
                                <NwButton
                                    asChild
                                    variant="glass"
                                    className="hidden md:inline-flex rounded-full bg-transparent px-5 py-1.5 text-sm font-medium backdrop-blur-none"
                                >
                                    <Link to="/login">{t('navbar.login')}</Link>
                                </NwButton>
                            )
                        )) : isLanding ? (
                            <NwButton
                                asChild
                                className="lp-cta-primary hidden md:inline-flex h-9 rounded-full px-5 text-sm font-medium shadow-none"
                            >
                                <Link to="/library" data-testid="home-start-writing-nav">{t('navbar.library')}</Link>
                            </NwButton>
                        ) : null}
                    </div>
                )}
            </div>
        </nav>
    )
}
