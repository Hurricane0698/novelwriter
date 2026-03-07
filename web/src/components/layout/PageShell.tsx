import { type ReactNode } from "react"
import { cn } from "@/lib/utils"
import { AnimatedBackground } from "@/components/layout/AnimatedBackground"
import { Navbar, type NavbarProps } from "@/components/layout/Navbar"

export type PageShellProps = {
    children: ReactNode
    className?: string
    mainClassName?: string
    /** Defaults to true. */
    showNavbar?: boolean
    navbarProps?: NavbarProps
    footer?: ReactNode
}

function getMainPaddingTop(navbarProps: NavbarProps | undefined): string | undefined {
    if (navbarProps?.position === "static") return undefined

    // Navbar is fixed by default; pad content so it doesn't render under it.
    if (navbarProps?.compact) return "pt-14"
    return "pt-16"
}

/** Shared page wrapper: animated background + optional navbar + consistent stacking. */
export function PageShell({
    children,
    className,
    mainClassName,
    showNavbar = true,
    navbarProps,
    footer,
}: PageShellProps) {
    return (
        <div
            className={cn(
                "min-h-screen flex flex-col font-sans text-foreground antialiased selection:bg-accent/20",
                className
            )}
        >
            <AnimatedBackground />
            {showNavbar ? <Navbar {...navbarProps} /> : null}
            <main className={cn("flex-1 flex flex-col", showNavbar ? getMainPaddingTop(navbarProps) : undefined, mainClassName)}>
                {children}
            </main>
            {footer ?? null}
        </div>
    )
}
