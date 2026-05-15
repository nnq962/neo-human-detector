import { useEffect, useState } from 'react'
import { getConfig } from '../../api/configApi'
import type { AppConfig } from '../../types/config'

type ZoneCheckMode = 'bottom_center' | 'center'
type SelectValue = string | number

type GeneralConfigState = Omit<AppConfig, 'zones'> & {
    detector: Omit<AppConfig['detector'], 'zone_check_mode'> & {
        zone_check_mode: ZoneCheckMode
    }
}

const baudrateOptions = [
    9600, 19200, 38400, 57600, 115200, 230400, 460800, 921600,
]

const zoneCheckModeOptions: ZoneCheckMode[] = ['bottom_center', 'center']

const defaultConfig: GeneralConfigState = {
    auto_start: true,
    detector: {
        source: 'rtsp://admin:phenikaaneo%40@192.168.0.150:554/Streaming/Channels/101',
        model_path: 'weights/head/yolo8n_rknn_model',
        conf: 0.5,
        zone_check_mode: 'bottom_center',
        confirm_enter_time: 5.0,
        confirm_exit_time: 5.0,
        pending_enter_miss_grace_time: 1.5,
        vid_stride: 1,
        verbose: false,
    },
    uart: {
        port: '/dev/ttyS4',
        baudrate: 115200,
    },
}

function isZoneCheckMode(value: string): value is ZoneCheckMode {
    return zoneCheckModeOptions.includes(value as ZoneCheckMode)
}

function toGeneralConfig(config: AppConfig): GeneralConfigState {
    return {
        auto_start: config.auto_start,
        detector: {
            ...config.detector,
            zone_check_mode: isZoneCheckMode(config.detector.zone_check_mode)
                ? config.detector.zone_check_mode
                : defaultConfig.detector.zone_check_mode,
        },
        uart: config.uart,
    }
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

function ToggleSwitch({
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

function NumberStepper({
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

function CustomSelect<T extends SelectValue>({
    label,
    value,
    options,
    onChange,
}: {
    label: string
    value: T
    options: T[]
    onChange: (value: T) => void
}) {
    const [isOpen, setIsOpen] = useState(false)

    return (
        <div className={`relative space-y-2 ${isOpen ? 'z-30' : 'z-0'}`}>
            <span className="text-sm font-semibold text-slate-700">{label}</span>
            <div className="relative">
                <button
                    type="button"
                    onClick={() => setIsOpen((current) => !current)}
                    onBlur={() => window.setTimeout(() => setIsOpen(false), 120)}
                    className="flex h-11 w-full min-w-0 items-center justify-between gap-3 rounded-lg border border-slate-200 bg-white py-0 pl-3 pr-2 text-left text-sm font-medium text-slate-900 shadow-sm outline-none transition-colors hover:border-slate-300 focus:border-sky-400 focus:ring-2 focus:ring-sky-100"
                >
                    <span className="truncate">{value}</span>
                    <span
                        className={`grid size-7 shrink-0 place-items-center rounded-md bg-slate-50 text-slate-500 transition-transform duration-200 ${isOpen ? 'rotate-180 text-slate-950' : ''
                            }`}
                    >
                        ▾
                    </span>
                </button>

                {isOpen ? (
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
                                {option}
                            </button>
                        ))}
                    </div>
                ) : null}
            </div>
        </div>
    )
}

type GeneralConfigProps = {
    reloadKey?: number
    onConfigChange?: (config: GeneralConfigState) => void
}

function GeneralConfig({ reloadKey = 0, onConfigChange }: GeneralConfigProps) {
    const [config, setConfig] = useState(defaultConfig)
    const [isLoading, setIsLoading] = useState(true)
    const [loadError, setLoadError] = useState('')

    useEffect(() => {
        let ignore = false

        const loadConfig = async () => {
            setIsLoading(true)
            setLoadError('')

            try {
                const apiConfig = await getConfig()

                if (!ignore) {
                    setConfig(toGeneralConfig(apiConfig))
                }
            } catch (error) {
                if (!ignore) {
                    setLoadError(error instanceof Error ? error.message : 'Unable to load config')
                }
            } finally {
                if (!ignore) {
                    setIsLoading(false)
                }
            }
        }

        loadConfig()

        return () => {
            ignore = true
        }
    }, [reloadKey])

    useEffect(() => {
        if (!isLoading) {
            onConfigChange?.(config)
        }
    }, [config, isLoading, onConfigChange])

    const inputClass =
        'h-11 w-full min-w-0 rounded-lg border border-slate-200 bg-white px-3 text-sm font-medium text-slate-900 shadow-sm outline-none transition-colors placeholder:text-slate-400 hover:border-slate-300 focus:border-sky-400 focus:ring-2 focus:ring-sky-100'

    const labelClass = 'text-sm font-semibold text-slate-700'

    return (
        <section className="rounded-xl border border-slate-200 bg-white p-4 shadow-[0_12px_36px_rgba(15,23,42,0.08)] sm:p-6">
            <div className="mb-6 flex flex-col gap-3 border-b border-slate-100 pb-5 sm:flex-row sm:items-center sm:justify-between">
                <div>
                    <h2 className="text-lg font-bold text-slate-950">General Config</h2>
                    <p className="mt-1 text-sm text-slate-500">
                        {isLoading
                            ? 'Loading detector and UART parameters...'
                            : loadError || 'Detector and UART parameters'}
                    </p>
                </div>

                <div className="w-full sm:w-52">
                    <ToggleSwitch
                        checked={config.auto_start}
                        label="Auto Start"
                        onChange={(checked) =>
                            setConfig((current) => ({ ...current, auto_start: checked }))
                        }
                    />
                </div>
            </div>

            <div className="grid gap-6 lg:grid-cols-[minmax(0,1fr)_320px]">
                <div className="space-y-5">
                    <div>
                        <h3 className="mb-4 text-sm font-bold uppercase tracking-wide text-slate-500">
                            Detector
                        </h3>

                        <div className="grid gap-4 rounded-xl border border-slate-100 bg-slate-50 p-4 md:grid-cols-2">
                            <label className="min-w-0 space-y-2 md:col-span-2">
                                <span className={labelClass}>Source</span>
                                <input
                                    type="text"
                                    value={config.detector.source}
                                    onChange={(event) =>
                                        setConfig((current) => ({
                                            ...current,
                                            detector: { ...current.detector, source: event.target.value },
                                        }))
                                    }
                                    className={inputClass}
                                />
                            </label>

                            <label className="min-w-0 space-y-2 md:col-span-2">
                                <span className={labelClass}>Model Path</span>
                                <input
                                    type="text"
                                    value={config.detector.model_path}
                                    onChange={(event) =>
                                        setConfig((current) => ({
                                            ...current,
                                            detector: {
                                                ...current.detector,
                                                model_path: event.target.value,
                                            },
                                        }))
                                    }
                                    className={inputClass}
                                />
                            </label>

                            <NumberStepper
                                label="Confidence"
                                value={config.detector.conf}
                                min={0}
                                max={1}
                                step={0.1}
                                onChange={(value) =>
                                    setConfig((current) => ({
                                        ...current,
                                        detector: {
                                            ...current.detector,
                                            conf: value,
                                        },
                                    }))
                                }
                            />

                            <NumberStepper
                                label="VID Stride"
                                value={config.detector.vid_stride}
                                min={1}
                                max={100}
                                step={1}
                                onChange={(value) =>
                                    setConfig((current) => ({
                                        ...current,
                                        detector: {
                                            ...current.detector,
                                            vid_stride: value,
                                        },
                                    }))
                                }
                            />

                            <NumberStepper
                                label="Confirm Enter Time"
                                value={config.detector.confirm_enter_time}
                                min={0}
                                max={120}
                                step={0.1}
                                onChange={(value) =>
                                    setConfig((current) => ({
                                        ...current,
                                        detector: {
                                            ...current.detector,
                                            confirm_enter_time: value,
                                        },
                                    }))
                                }
                            />

                            <NumberStepper
                                label="Confirm Exit Time"
                                value={config.detector.confirm_exit_time}
                                min={0}
                                max={120}
                                step={0.1}
                                onChange={(value) =>
                                    setConfig((current) => ({
                                        ...current,
                                        detector: {
                                            ...current.detector,
                                            confirm_exit_time: value,
                                        },
                                    }))
                                }
                            />

                            <NumberStepper
                                label="Pending Enter Miss Grace"
                                value={config.detector.pending_enter_miss_grace_time}
                                min={0}
                                max={120}
                                step={0.1}
                                onChange={(value) =>
                                    setConfig((current) => ({
                                        ...current,
                                        detector: {
                                            ...current.detector,
                                            pending_enter_miss_grace_time: value,
                                        },
                                    }))
                                }
                            />

                            <CustomSelect
                                label="Zone Check Mode"
                                value={config.detector.zone_check_mode}
                                options={zoneCheckModeOptions}
                                onChange={(value) =>
                                    setConfig((current) => ({
                                        ...current,
                                        detector: {
                                            ...current.detector,
                                            zone_check_mode: value,
                                        },
                                    }))
                                }
                            />

                            <div className="space-y-2">
                                <span className={labelClass}>Verbose</span>
                                <ToggleSwitch
                                    checked={config.detector.verbose}
                                    onChange={(checked) =>
                                        setConfig((current) => ({
                                            ...current,
                                            detector: { ...current.detector, verbose: checked },
                                        }))
                                    }
                                />
                            </div>
                        </div>
                    </div>
                </div>

                <div>
                    <h3 className="mb-4 text-sm font-bold uppercase tracking-wide text-slate-500">
                        UART
                    </h3>

                    <div className="space-y-4 rounded-xl border border-slate-100 bg-slate-50 p-4">
                        <label className="block space-y-2">
                            <span className={labelClass}>Port</span>
                            <input
                                type="text"
                                value={config.uart.port}
                                onChange={(event) =>
                                    setConfig((current) => ({
                                        ...current,
                                        uart: { ...current.uart, port: event.target.value },
                                    }))
                                }
                                className={inputClass}
                            />
                        </label>

                        <CustomSelect
                            label="Baudrate"
                            value={config.uart.baudrate}
                            options={baudrateOptions}
                            onChange={(value) =>
                                setConfig((current) => ({
                                    ...current,
                                    uart: { ...current.uart, baudrate: value },
                                }))
                            }
                        />
                    </div>
                </div>
            </div>
        </section>
    )
}

export default GeneralConfig
