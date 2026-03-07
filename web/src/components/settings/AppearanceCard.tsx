import { Moon, Sun } from "lucide-react"
import { useTheme } from "@/hooks/useTheme"
import { cn } from "@/lib/utils"

export function AppearanceCard() {
    const { theme, setTheme } = useTheme()

    return (
        <div className="rounded-2xl border border-[var(--nw-glass-border)] bg-[var(--nw-glass-bg)] backdrop-blur-xl p-6 flex flex-col gap-4">
            <span className="text-sm font-medium">主题模式</span>
            <div className="flex gap-4">
                <button
                    type="button"
                    aria-pressed={theme === 'dark'}
                    onClick={() => setTheme('dark')}
                    className={cn(
                        "flex-1 h-[100px] rounded-xl flex flex-col items-center justify-center gap-2 transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent focus-visible:ring-offset-2 focus-visible:ring-offset-background",
                        theme === 'dark'
                            ? "bg-accent/[0.08] border-2 border-accent text-accent"
                            : "bg-[var(--nw-glass-bg)] border border-[var(--nw-glass-border)] text-muted-foreground hover:border-[var(--nw-glass-border-hover)]"
                    )}
                >
                    <Moon className="h-6 w-6" />
                    <span className={cn("text-[13px]", theme === 'dark' ? "font-semibold" : "font-normal")}>
                        深色模式
                    </span>
                </button>
                <button
                    type="button"
                    aria-pressed={theme === 'light'}
                    onClick={() => setTheme('light')}
                    className={cn(
                        "flex-1 h-[100px] rounded-xl flex flex-col items-center justify-center gap-2 transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent focus-visible:ring-offset-2 focus-visible:ring-offset-background",
                        theme === 'light'
                            ? "bg-accent/[0.08] border-2 border-accent text-accent"
                            : "bg-[var(--nw-glass-bg)] border border-[var(--nw-glass-border)] text-muted-foreground hover:border-[var(--nw-glass-border-hover)]"
                    )}
                >
                    <Sun className="h-6 w-6" />
                    <span className={cn("text-[13px]", theme === 'light' ? "font-semibold" : "font-normal")}>
                        浅色模式
                    </span>
                </button>
            </div>
        </div>
    )
}
