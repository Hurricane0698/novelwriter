import { useRef, useState } from "react"
import { ConfirmTone } from "@/components/ui/confirm-dialog"

type DialogMode = "confirm" | "alert"

interface DialogState {
    mode: DialogMode
    title: string
    description?: string
    confirmText?: string
    cancelText?: string
    tone?: ConfirmTone
    resolve: (value: boolean) => void
}

interface DialogOptions {
    title: string
    description?: string
    confirmText?: string
    cancelText?: string
    tone?: ConfirmTone
}

export function useConfirmDialog() {
    const [state, setState] = useState<DialogState | null>(null)
    const queueRef = useRef<DialogState[]>([])

    const enqueue = (next: DialogState) => {
        setState((current) => {
            if (current) {
                queueRef.current.push(next)
                return current
            }
            return next
        })
    }

    const showNext = () => {
        const next = queueRef.current.shift() ?? null
        setState(next)
    }

    const confirm = (options: DialogOptions) =>
        new Promise<boolean>((resolve) => {
            enqueue({
                mode: "confirm",
                resolve,
                ...options,
            })
        })

    const alert = (options: DialogOptions) =>
        new Promise<void>((resolve) => {
            enqueue({
                mode: "alert",
                resolve: () => resolve(),
                ...options,
            })
        })

    const handleConfirm = () => {
        if (!state) return
        state.resolve(true)
        showNext()
    }

    const handleClose = () => {
        if (!state) return
        if (state.mode === "confirm") {
            state.resolve(false)
        }
        showNext()
    }

    const dialogProps = {
        open: Boolean(state),
        title: state?.title ?? "",
        description: state?.description,
        confirmText: state?.confirmText ?? (state?.mode === "alert" ? "知道了" : "确认"),
        cancelText: state?.cancelText ?? "取消",
        showCancel: state?.mode === "confirm",
        tone: state?.tone ?? "default",
        onConfirm: handleConfirm,
        onClose: handleClose,
    }

    return { confirm, alert, dialogProps }
}
