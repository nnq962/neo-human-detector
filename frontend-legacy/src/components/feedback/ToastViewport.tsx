import type { Toast } from '../../types/toast'

type ToastViewportProps = {
    toasts: Toast[]
}

const variantClass = {
    success: 'border-emerald-200 bg-emerald-50 text-emerald-800',
    error: 'border-rose-200 bg-rose-50 text-rose-800',
    info: 'border-sky-200 bg-sky-50 text-sky-800',
    warning: 'border-amber-200 bg-amber-50 text-amber-800',
}

const variantIcon = {
    success: '✓',
    error: '!',
    info: 'i',
    warning: '!',
}

function ToastViewport({ toasts }: ToastViewportProps) {
    return (
        <div className="pointer-events-none fixed left-1/2 top-4 z-[100] flex w-[calc(100%-2rem)] max-w-md -translate-x-1/2 flex-col items-center gap-2">
            {toasts.map((toast) => (
                <div
                    key={toast.id}
                    className={`pointer-events-auto flex min-h-11 w-full items-center gap-3 rounded-lg border px-4 py-3 text-sm font-semibold shadow-[0_18px_40px_rgba(15,23,42,0.18)] backdrop-blur ${toast.isExiting
                            ? 'animate-[toast-slide-up_220ms_ease-in_forwards]'
                            : 'animate-[toast-slide-down_220ms_ease-out]'
                        } ${variantClass[toast.variant]}`}
                >
                    <span className="grid size-5 shrink-0 place-items-center rounded-full bg-white/80 text-xs shadow-sm">
                        {variantIcon[toast.variant]}
                    </span>
                    <span className="min-w-0 flex-1">{toast.message}</span>
                </div>
            ))}
        </div>
    )
}

export default ToastViewport
