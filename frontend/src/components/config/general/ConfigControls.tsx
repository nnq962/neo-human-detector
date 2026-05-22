import { useState } from 'react'
import type { SelectValue } from './types'

export function ToggleSwitch({
    checked,
    label,
    onChange,
}: {
    checked: boolean
    label?: string
    onChange: (checked: boolean) => void
}) {
    return (
        <label
            className={`flex h-11 items-center gap-4 rounded-lg border border-slate-200 bg-white px-3 shadow-sm transition-colors hover:border-slate-300 ${label ? 'justify-between' : 'justify-end'
                }`}
        >
            {label ? <span className="text-sm font-semibold text-slate-800">{label}</span> : null}
            <input
                type="checkbox"
                checked={checked}
                onChange={(event) => onChange(event.target.checked)}
                className="peer sr-only"
            />
            <span className="relative h-7 w-12 rounded-full bg-slate-200 transition-colors after:absolute after:left-1 after:top-1 after:size-5 after:rounded-full after:bg-white after:shadow-sm after:transition-transform peer-checked:bg-emerald-500 peer-checked:after:translate-x-5 peer-focus-visible:ring-2 peer-focus-visible:ring-emerald-500 peer-focus-visible:ring-offset-2" />
        </label>
    )
}

function clampValue(value: number, min: number, max: number) {
    if (Number.isNaN(value)) {
        return min
    }

    return Math.min(Math.max(value, min), max)
}

function getStepPrecision(step: number) {
    const [, decimals = ''] = step.toString().split('.')

    return decimals.length
}

function roundByStep(value: number, step: number) {
    const precision = getStepPrecision(step)
    const factor = 10 ** precision

    return Math.round(value * factor) / factor
}

export function NumberStepper({
    label,
    value,
    min,
    max,
    step,
    onChange,
}: {
    label: string
    value: number
    min: number
    max: number
    step: number
    onChange: (value: number) => void
}) {
    const updateValue = (nextValue: number) => {
        onChange(roundByStep(clampValue(nextValue, min, max), step))
    }

    return (
        <label className="space-y-2">
            <span className="text-sm font-semibold text-slate-700">{label}</span>
            <div className="flex h-11 overflow-hidden rounded-lg border border-slate-200 bg-white shadow-sm transition-colors focus-within:border-sky-400 focus-within:ring-2 focus-within:ring-sky-100 hover:border-slate-300">
                <input
                    type="number"
                    min={min}
                    max={max}
                    step={step}
                    value={Number.isNaN(value) ? '' : value}
                    onChange={(event) => onChange(Number(event.target.value))}
                    onBlur={(event) => updateValue(Number(event.target.value))}
                    className="min-w-0 flex-1 bg-transparent px-3 text-sm font-medium text-slate-900 outline-none [appearance:textfield] [&::-webkit-inner-spin-button]:appearance-none [&::-webkit-outer-spin-button]:appearance-none"
                />

                <div className="flex border-l border-slate-200 bg-slate-50">
                    <button
                        type="button"
                        onClick={() => updateValue(value - step)}
                        className="grid w-10 place-items-center text-base font-bold text-slate-500 transition-colors hover:bg-white hover:text-slate-950 active:bg-slate-100"
                    >
                        -
                    </button>
                    <button
                        type="button"
                        onClick={() => updateValue(value + step)}
                        className="grid w-10 place-items-center border-l border-slate-200 text-base font-bold text-slate-500 transition-colors hover:bg-white hover:text-slate-950 active:bg-slate-100"
                    >
                        +
                    </button>
                </div>
            </div>
        </label>
    )
}

export function CustomSelect<T extends SelectValue>({
    label,
    value,
    options,
    disabled = false,
    placeholder = '',
    getOptionLabel,
    onChange,
}: {
    label?: string
    value: T
    options: T[]
    disabled?: boolean
    placeholder?: string
    getOptionLabel?: (value: T) => string
    onChange: (value: T) => void
}) {
    const [isOpen, setIsOpen] = useState(false)
    const selectedLabel = getOptionLabel?.(value) || String(value || placeholder)

    return (
        <div className={`relative space-y-2 ${isOpen ? 'z-30' : 'z-0'}`}>
            {label ? <span className="text-sm font-semibold text-slate-700">{label}</span> : null}
            <div className="relative">
                <button
                    type="button"
                    onClick={() => {
                        if (!disabled) {
                            setIsOpen((current) => !current)
                        }
                    }}
                    onBlur={() => window.setTimeout(() => setIsOpen(false), 120)}
                    disabled={disabled}
                    className="flex h-11 w-full min-w-0 items-center justify-between gap-3 rounded-lg border border-slate-200 bg-white py-0 pl-3 pr-2 text-left text-sm font-medium text-slate-900 shadow-sm outline-none transition-colors hover:border-slate-300 focus:border-sky-400 focus:ring-2 focus:ring-sky-100 disabled:cursor-not-allowed disabled:bg-slate-100 disabled:text-slate-500"
                >
                    <span className="truncate">{selectedLabel}</span>
                    <span
                        className={`grid size-7 shrink-0 place-items-center rounded-md bg-slate-50 text-slate-500 transition-transform duration-200 ${isOpen ? 'rotate-180 text-slate-950' : ''
                            }`}
                    >
                        ▾
                    </span>
                </button>

                {isOpen && !disabled ? (
                    <div className="no-scrollbar absolute left-0 right-0 top-[calc(100%+0.5rem)] z-50 max-h-56 overflow-auto rounded-lg border border-slate-200 bg-white p-1 shadow-[0_18px_36px_rgba(15,23,42,0.14)]">
                        {options.map((option) => (
                            <button
                                key={option}
                                type="button"
                                onMouseDown={(event) => event.preventDefault()}
                                onClick={() => {
                                    onChange(option)
                                    setIsOpen(false)
                                }}
                                className={`flex h-10 w-full items-center rounded-md px-3 text-left text-sm font-semibold transition-colors ${option === value
                                        ? 'bg-sky-50 text-sky-700'
                                        : 'text-slate-700 hover:bg-slate-50 hover:text-slate-950'
                                    }`}
                            >
                                {getOptionLabel?.(option) || option}
                            </button>
                        ))}
                    </div>
                ) : null}
            </div>
        </div>
    )
}
