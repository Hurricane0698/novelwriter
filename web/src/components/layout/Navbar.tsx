import { type ReactNode } from "react"
import { Link, useLocation } from "react-router-dom"
import { useAuth } from "@/contexts/AuthContext"
import { Avatar, AvatarFallback } from "@/components/ui/avatar"
import { cn } from "@/lib/utils"
import { NwButton } from "@/components/ui/nw-button"

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
    const { pathname } = useLocation()
    const isLanding = pathname === "/"

    const navPositionClass =
        position === "fixed" ? "fixed inset-x-0 top-0 z-50" : "w-full"
    const heightClass = compact ? "h-14" : "h-16"
    const paddingClass = compact ? "px-6" : "px-12"
    const brandSizeClass = compact ? "text-lg" : "text-xl"

    return (
        <nav
            className={cn(
                navPositionClass,
                heightClass,
                "border-b border-[var(--nw-glass-border)] bg-[hsl(var(--background)/0.60)] backdrop-blur-xl"
            )}
        >
            <div className={`mx-auto h-full flex items-center justify-between ${paddingClass}`}>
                {leftContent ?? (
                    <div className="flex items-center gap-6">
                        <Link to="/" className={`font-mono ${brandSizeClass} font-bold text-foreground hover:opacity-80 transition-opacity`}>
                            NovWr
                        </Link>
                        {!hideLinks ? (
                            <div className="hidden md:flex items-center gap-6 text-sm font-medium text-muted-foreground">
                                {isLanding ? (
                                    <a href="#features" className="hover:text-foreground transition-colors">功能</a>
                                ) : (
                                    <>
                                        <Link
                                            to="/library"
                                            className="hover:text-foreground transition-colors"
                                        >
                                            作品库
                                        </Link>
                                        <Link
                                            to="/settings"
                                            className="hover:text-foreground transition-colors"
                                        >
                                            设置
                                        </Link>
                                    </>
                                )}
                            </div>
                        ) : null}
                    </div>
                )}
                {rightContent ?? (
                    <div className="flex items-center gap-4">
                        {isLoggedIn && user ? (
                            <Link to="/settings">
                                <Avatar className="h-8 w-8 transition-opacity hover:opacity-80">
                                    <AvatarFallback>{user.username[0]?.toUpperCase()}</AvatarFallback>
                                </Avatar>
                            </Link>
                        ) : (
                            <NwButton
                                asChild
                                variant="glass"
                                className="hidden md:inline-flex rounded-full bg-transparent px-5 py-1.5 text-sm font-medium backdrop-blur-none"
                            >
                                <Link to="/login">登录</Link>
                            </NwButton>
                        )}
                    </div>
                )}
            </div>
        </nav>
    )
}
