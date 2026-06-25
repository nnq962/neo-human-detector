import type { ReactNode } from 'react'

export function SectionShell({
    title,
    children,
    className = '',
}: {
    title: string
    children: ReactNode
    className?: string
}) {
    return (
        <div>
            <h3 className="mb-4 text-sm font-bold uppercase tracking-wide text-slate-500">
                {title}
            </h3>
            <div className={`rounded-xl border border-slate-100 bg-slate-50 p-4 ${className}`}>
                {children}
            </div>
        </div>
    )
}

