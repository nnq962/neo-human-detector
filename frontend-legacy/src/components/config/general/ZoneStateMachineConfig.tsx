import { useEffect, useState } from 'react'
import {
    getZoneStateMachineConfig,
    updateZoneStateMachineConfig,
} from '../../../api/zoneStateMachineApi'
import { useToast } from '../../../hooks/useToast'
import type { ZoneStateMachineConfig as ZoneStateMachineConfigValue } from '../../../types/config'
import { NumberStepper } from './ConfigControls'
import { SectionShell } from './SectionShell'

const defaultZoneStateMachineConfig: ZoneStateMachineConfigValue = {
    confirm_enter_time: 5.0,
    confirm_exit_time: 5.0,
    pending_enter_miss_grace_time: 1.5,
}

function ZoneStateMachineConfig() {
    const toast = useToast()
    const [config, setConfig] = useState<ZoneStateMachineConfigValue>(defaultZoneStateMachineConfig)
    const [initialConfig, setInitialConfig] = useState<ZoneStateMachineConfigValue>(defaultZoneStateMachineConfig)
    const [isLoading, setIsLoading] = useState(true)
    const [isSaving, setIsSaving] = useState(false)
    const [loadError, setLoadError] = useState('')

    useEffect(() => {
        let ignore = false

        const loadConfig = async () => {
            setIsLoading(true)
            setLoadError('')

            try {
                const apiConfig = await getZoneStateMachineConfig()

                if (!ignore) {
                    setConfig(apiConfig)
                    setInitialConfig(apiConfig)
                }
            } catch (error) {
                const message = error instanceof Error
                    ? error.message
                    : 'Unable to load zones state machine config.'

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

    const updateConfig = (patch: Partial<ZoneStateMachineConfigValue>) => {
        setConfig((current) => ({
            ...current,
            ...patch,
        }))
    }

    const saveConfig = async () => {
        setIsSaving(true)

        try {
            const savedConfig = await updateZoneStateMachineConfig(config)

            setConfig(savedConfig)
            setInitialConfig(savedConfig)
            toast.success('Zones state machine config saved.')
        } catch (error) {
            toast.error(
                error instanceof Error
                    ? error.message
                    : 'Unable to save zones state machine config.',
            )
        } finally {
            setIsSaving(false)
        }
    }

    const cancelChanges = () => {
        setConfig(initialConfig)
        toast.info('Zones state machine changes discarded.')
    }

    return (
        <SectionShell title="Zone State Machine" className="grid gap-4 md:grid-cols-2">
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
                    {isLoading ? 'Loading zones state machine config...' : loadError}
                </p>
            ) : null}

            <NumberStepper
                label="Confirm Enter Time"
                value={config.confirm_enter_time}
                min={0}
                max={120}
                step={0.1}
                onChange={(value) => updateConfig({ confirm_enter_time: value })}
            />

            <NumberStepper
                label="Confirm Exit Time"
                value={config.confirm_exit_time}
                min={0}
                max={120}
                step={0.1}
                onChange={(value) => updateConfig({ confirm_exit_time: value })}
            />

            <NumberStepper
                label="Pending Enter Miss Grace"
                value={config.pending_enter_miss_grace_time}
                min={0}
                max={120}
                step={0.1}
                onChange={(value) => updateConfig({ pending_enter_miss_grace_time: value })}
            />
        </SectionShell>
    )
}

export default ZoneStateMachineConfig
