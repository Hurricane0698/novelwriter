import { LogOut, MessageSquarePlus } from "lucide-react"
import { useState } from "react"
import { useAuth } from "@/contexts/AuthContext"
import { api } from "@/services/api"
import { NwButton } from "@/components/ui/nw-button"
import { FeedbackForm, type FeedbackAnswers } from "@/components/feedback/FeedbackForm"

const IS_HOSTED = (import.meta.env.VITE_DEPLOY_MODE || "selfhost") === "hosted"

export function AccountCard() {
    const { user, logout, refreshQuota } = useAuth()
    const [showForm, setShowForm] = useState(false)
    const [submitting, setSubmitting] = useState(false)

    if (!user) return null

    const displayName = user.nickname || user.username
    const initial = displayName[0]?.toUpperCase() ?? "U"

    const handleFeedback = async (answers: FeedbackAnswers) => {
        setSubmitting(true)
        try {
            await api.submitFeedback(answers)
            await refreshQuota()
            setShowForm(false)
        } catch {
            // Could add error toast here
        } finally {
            setSubmitting(false)
        }
    }

    return (
        <>
            <div className="rounded-2xl border border-[var(--nw-glass-border)] bg-[var(--nw-glass-bg)] backdrop-blur-xl p-6 flex flex-col gap-5">
                {/* Profile row */}
                <div className="flex items-center gap-4">
                    <div className="h-14 w-14 rounded-full bg-[var(--nw-glass-bg-hover)] flex items-center justify-center shrink-0">
                        <span className="font-mono text-[22px] font-semibold">{initial}</span>
                    </div>
                    <div className="flex flex-col gap-1 min-w-0">
                        <span className="text-base font-semibold truncate">{displayName}</span>
                        <span className="text-sm text-muted-foreground truncate">{user.role}</span>
                    </div>
                </div>

                {/* Divider */}
                <div className="h-px bg-[var(--nw-glass-bg-hover)]" />

                {/* Info rows */}
                <div className="flex items-center justify-between">
                    <span className="text-[13px] text-muted-foreground">昵称</span>
                    <span className="text-[13px]">{displayName}</span>
                </div>

                {/* Quota & feedback — hosted mode only */}
                {IS_HOSTED && (
                    <>
                        <div className="flex items-center justify-between">
                            <span className="text-[13px] text-muted-foreground">剩余生成次数</span>
                            <span className={`text-[13px] font-mono ${user.generation_quota <= 0 ? 'text-[hsl(var(--color-danger))]' : ''}`}>
                                {user.generation_quota}
                            </span>
                        </div>

                        {!user.feedback_submitted && (
                            <>
                                <div className="h-px bg-[var(--nw-glass-bg-hover)]" />
                                <div className="flex flex-col gap-2">
                                    <span className="text-[13px] text-muted-foreground">
                                        提交反馈可获得额外生成额度
                                    </span>
                                    <NwButton
                                        variant="glass"
                                        onClick={() => setShowForm(true)}
                                        className="h-9 rounded-lg text-sm"
                                    >
                                        <MessageSquarePlus className="h-4 w-4 mr-2" />
                                        提交反馈
                                    </NwButton>
                                </div>
                            </>
                        )}
                    </>
                )}

                {/* Divider */}
                <div className="h-px bg-[var(--nw-glass-bg-hover)]" />

                {/* Logout button */}
                <button
                    type="button"
                    onClick={logout}
                    className="flex items-center justify-center gap-2 h-10 rounded-[10px] border border-[hsl(var(--color-danger)/0.25)] text-[hsl(var(--color-danger))] hover:bg-[hsl(var(--color-danger)/0.08)] transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[hsl(var(--color-danger))] focus-visible:ring-offset-2 focus-visible:ring-offset-background"
                >
                    <LogOut className="h-4 w-4" />
                    <span className="text-sm font-medium">退出登录</span>
                </button>
            </div>

            {showForm && (
                <FeedbackForm
                    onSubmit={handleFeedback}
                    onCancel={() => setShowForm(false)}
                    submitting={submitting}
                />
            )}
        </>
    )
}
