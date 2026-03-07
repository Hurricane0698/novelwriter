import { Button } from "@/components/ui/button"

export type ConfirmTone = "default" | "destructive" | "secondary"

interface ConfirmDialogProps {
    open: boolean
    title: string
    description?: string
    confirmText?: string
    cancelText?: string
    showCancel?: boolean
    tone?: ConfirmTone
    onConfirm: () => void
    onClose: () => void
}

const toneToVariant = (tone?: ConfirmTone) => {
    if (tone === "destructive") return "destructive"
    if (tone === "secondary") return "secondary"
    return "default"
}

export function ConfirmDialog({
    open,
    title,
    description,
    confirmText = "确认",
    cancelText = "取消",
    showCancel = true,
    tone = "default",
    onConfirm,
    onClose,
}: ConfirmDialogProps) {
    if (!open) return null

    return (
        <div
            className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 backdrop-blur-sm"
            onClick={() => {
                if (showCancel) onClose()
            }}
        >
            <div
                className="w-full max-w-md mx-4 rounded-xl border bg-background shadow-xl"
                onClick={(event) => event.stopPropagation()}
                data-testid="confirm-dialog"
            >
                <div className="px-6 py-4 border-b">
                    <h3 className="text-lg font-semibold text-foreground">{title}</h3>
                    {description && (
                        <p className="mt-2 text-sm text-muted-foreground whitespace-pre-wrap">
                            {description}
                        </p>
                    )}
                </div>
                <div className="px-6 py-4 flex justify-end gap-2">
                    {showCancel && (
                        <Button variant="outline" onClick={onClose} data-testid="confirm-cancel">
                            {cancelText}
                        </Button>
                    )}
                    <Button variant={toneToVariant(tone)} onClick={onConfirm} data-testid="confirm-ok">
                        {confirmText}
                    </Button>
                </div>
            </div>
        </div>
    )
}
