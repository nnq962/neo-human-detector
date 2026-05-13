import { createContext, useCallback, useMemo, useState } from 'react'
import type { ReactNode } from 'react'
import type { Toast, ToastVariant } from '../../types/toast'
import ToastViewport from './ToastViewport'

type ToastInput = {
    message: string
    variant?: ToastVariant
}

type ToastContextValue = {
    showToast: (toast: ToastInput) => void
    success: (message: string) => void
    error: (message: string) => void
    info: (message: string) => void
    warning: (message: string) => void
}

export const ToastContext = createContext<ToastContextValue | null>(null)

type ToastProviderProps = {
    children: ReactNode
}

function createToastId() {
    return `${Date.now()}-${Math.random().toString(16).slice(2)}`
}

export function ToastProvider({ children }: ToastProviderProps) {
    const [toasts, setToasts] = useState<Toast[]>([])

    const showToast = useCallback(({ message, variant = 'info' }: ToastInput) => {
        const toast: Toast = {
            id: createToastId(),
            message,
            variant,
        }

        setToasts((currentToasts) => [...currentToasts, toast].slice(-3))
        window.setTimeout(() => {
            setToasts((currentToasts) =>
                currentToasts.map((currentToast) =>
                    currentToast.id === toast.id
                        ? {
                            ...currentToast,
                            isExiting: true,
                        }
                        : currentToast,
                ),
            )
        }, 2800)
        window.setTimeout(() => {
            setToasts((currentToasts) =>
                currentToasts.filter((currentToast) => currentToast.id !== toast.id),
            )
        }, 3000)
    }, [])

    const value = useMemo<ToastContextValue>(() => ({
        showToast,
        success: (message) => showToast({ message, variant: 'success' }),
        error: (message) => showToast({ message, variant: 'error' }),
        info: (message) => showToast({ message, variant: 'info' }),
        warning: (message) => showToast({ message, variant: 'warning' }),
    }), [showToast])

    return (
        <ToastContext.Provider value={value}>
            {children}
            <ToastViewport toasts={toasts} />
        </ToastContext.Provider>
    )
}
