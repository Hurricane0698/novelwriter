import { Link } from "react-router-dom"
import { useAuth } from "@/contexts/AuthContext"
import { NwButton } from "@/components/ui/nw-button"

export function Hero() {
    const { isLoggedIn } = useAuth()

    return (
        <section className="flex w-full min-h-[600px] items-center justify-center px-12 py-[120px]">
            <div className="flex max-w-[800px] flex-col items-center gap-8 text-center">
                <h1 className="font-mono text-[56px] font-bold leading-[1.2] text-foreground">
                    在完整的世界观里续写你的故事
                </h1>

                <p className="max-w-[640px] font-sans text-lg leading-[1.6] text-muted-foreground">
                    NovWr 通过世界模型驱动 AI
                    续写——不是盲目生成，而是真正理解你笔下的角色、关系与规则，写出连贯的长篇故事。
                </p>

                <NwButton
                    asChild
                    variant="accent"
                    className="rounded-full px-8 py-3.5 text-base font-medium shadow-[0_0_24px_hsl(var(--accent)/0.4)]"
                >
                    <Link to={isLoggedIn ? "/library" : "/login"}>开始写作</Link>
                </NwButton>
            </div>
        </section>
    )
}
