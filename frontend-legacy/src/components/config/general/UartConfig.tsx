import { useEffect, useState } from 'react'
import { getUartConfig, updateUartConfig } from '../../../api/uartApi'
import { useToast } from '../../../hooks/useToast'
import type { UartConfig as UartConfigValue } from '../../../types/config'
import { CustomSelect } from './ConfigControls'
import { baudrateOptions } from './options'
import { SectionShell } from './SectionShell'

type UartConfigProps = {
    inputClass: string
    labelClass: string
}

const defaultUartConfig: UartConfigValue = {
    port: '/dev/ttyS4',
    baudrate: 115200,
}

function UartConfig({ inputClass, labelClass }: UartConfigProps) {
    const toast = useToast()
    const [uart, setUart] = useState<UartConfigValue>(defaultUartConfig)
    const [initialUart, setInitialUart] = useState<UartConfigValue>(defaultUartConfig)
    const [isLoading, setIsLoading] = useState(true)
    const [isSaving, setIsSaving] = useState(false)
    const [loadError, setLoadError] = useState('')

    useEffect(() => {
        let ignore = false

        const loadConfig = async () => {
            setIsLoading(true)
            setLoadError('')

            try {
                const config = await getUartConfig()

                if (!ignore) {
                    setUart(config)
                    setInitialUart(config)
                }
            } catch (error) {
                const message = error instanceof Error ? error.message : 'Unable to load UART config.'

                if (!ignore) {
                    setLoadError(message)
                    toast.error(message)
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
    }, [toast])

    const updateUart = (patch: Partial<UartConfigValue>) => {
        setUart((current) => ({
            ...current,
            ...patch,
        }))
    }

    const saveConfig = async () => {
        if (!uart.port.trim()) {
            toast.error('UART port is required.')
            return
        }

        setIsSaving(true)

        try {
            const savedConfig = await updateUartConfig({
                ...uart,
                port: uart.port.trim(),
            })

            setUart(savedConfig)
            setInitialUart(savedConfig)
            toast.success('UART config saved.')
        } catch (error) {
            toast.error(error instanceof Error ? error.message : 'Unable to save UART config.')
        } finally {
            setIsSaving(false)
        }
    }

    const cancelChanges = () => {
        setUart(initialUart)
        toast.info('UART changes discarded.')
    }

    return (
        <SectionShell title="UART" className="grid gap-4 md:grid-cols-[minmax(0,1fr)_240px] md:items-end">
            <div className="flex w-full gap-3 md:col-span-2 sm:w-auto">
                <button
                    type="button"
                    onClick={saveConfig}
                    disabled={isSaving || isLoading}
                    className="h-11 flex-1 rounded-lg border border-emerald-200 bg-emerald-50 px-4 text-sm font-semibold text-emerald-700 shadow-sm transition-colors hover:border-emerald-300 hover:bg-emerald-100 active:bg-emerald-200 disabled:cursor-not-allowed disabled:opacity-60 sm:flex-none"
                >
                    {isSaving ? 'Saving...' : 'Save'}
                </button>
                <button
                    type="button"
                    onClick={cancelChanges}
                    disabled={isSaving || isLoading}
                    className="h-11 flex-1 rounded-lg border border-amber-200 bg-amber-50 px-4 text-sm font-semibold text-amber-700 shadow-sm transition-colors hover:border-amber-300 hover:bg-amber-100 active:bg-amber-200 disabled:cursor-not-allowed disabled:opacity-60 sm:flex-none"
                >
                    Cancel
                </button>
            </div>

            {isLoading || loadError ? (
                <p className="text-sm font-medium text-slate-500 md:col-span-2">
                    {isLoading ? 'Loading UART config...' : loadError}
                </p>
            ) : null}

            <label className="block min-w-0 space-y-2">
                <span className={labelClass}>Port</span>
                <input
                    type="text"
                    value={uart.port}
                    onChange={(event) => updateUart({ port: event.target.value })}
                    className={inputClass}
                />
            </label>

            <CustomSelect
                label="Baudrate"
                value={uart.baudrate}
                options={baudrateOptions}
                onChange={(value) => updateUart({ baudrate: value })}
            />
        </SectionShell>
    )
}

export default UartConfig
