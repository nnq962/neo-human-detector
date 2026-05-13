export type ToastVariant = 'success' | 'error' | 'info' | 'warning'

export interface Toast {
    id: string
    message: string
    variant: ToastVariant
    isExiting?: boolean
}
