import { Globe, Brain, GitBranch, type LucideIcon } from "lucide-react"
import { GlassCard } from "@/components/GlassCard"

const features: {
    title: string
    description: string
    icon: LucideIcon
}[] = [
    {
        title: "世界模型",
        description:
            "构建角色、关系、规则体系——AI 基于结构化知识图谱理解你的世界，而非简单的上下文窗口。",
        icon: Globe,
    },
    {
        title: "语境感知续写",
        description:
            "不是盲目生成，而是基于世界模型的连贯写作。AI 知道谁在哪里、发生了什么、规则是什么。",
        icon: Brain,
    },
    {
        title: "多版本对比",
        description:
            "一次生成多个续写版本，对比选择最佳方案。快速迭代，找到最契合故事走向的那一版。",
        icon: GitBranch,
    },
]

export function Features() {
    return (
        <section id="features" className="w-full px-12 py-24">
            <div className="mx-auto flex max-w-6xl flex-col items-center gap-12">
                {/* Header */}
                <div className="flex flex-col items-center gap-3 text-center">
                    <h2 className="font-mono text-4xl font-bold text-foreground">
                        核心能力
                    </h2>
                    <p className="max-w-[500px] font-sans text-base leading-relaxed text-muted-foreground">
                        不只是文本生成器——NovWr 让 AI 真正理解你的故事世界
                    </p>
                </div>

                {/* Cards */}
                <div className="grid w-full grid-cols-1 gap-6 md:grid-cols-3">
                    {features.map((feature) => (
                        <GlassCard
                            key={feature.title}
                            hoverable
                            className="p-8 flex flex-col gap-5"
                        >
                            <div className="flex h-12 w-12 items-center justify-center rounded-xl bg-accent/10 ring-1 ring-accent/20">
                                <feature.icon className="h-6 w-6 text-accent" />
                            </div>
                            <h3 className="font-mono text-xl font-semibold text-foreground">
                                {feature.title}
                            </h3>
                            <p className="font-sans text-sm leading-[1.6] text-muted-foreground">
                                {feature.description}
                            </p>
                        </GlassCard>
                    ))}
                </div>
            </div>
        </section>
    )
}
