import { useEffect, useState } from 'react'
import { getDetectorConfig, updateDetectorConfig } from '../../../api/detectorApi'
import { useToast } from '../../../hooks/useToast'
import { notifyRestartRequired } from '../../../lib/restartRequiredEvents'
import type { DetectorConfig } from '../../../types/config'
import { CustomSelect, NumberStepper, ToggleSwitch } from './ConfigControls'
import { batchSizeOptions, detectorModeOptions, modelSizeOptions } from './options'
import { SectionShell } from './SectionShell'

const defaultDetectorConfig: DetectorConfig = {
    mode: 'head',
    model_size: 'nano',
    batch_size: 2,
    conf: 0.5,
    vid_stride: 1,
    verbose: false,
}

function hasRestartOnlyDetectorChanges(current: DetectorConfig, initial: DetectorConfig) {
    return current.mode !== initial.mode ||
        current.model_size !== initial.model_size ||
        current.batch_size !== initial.batch_size ||
        current.conf !== initial.conf ||
        current.vid_stride !== initial.vid_stride
}

function AIConfig() {
    const toast = useToast()
    const [autoStart, setAutoStart] = useState(false)
    const [detector, setDetector] = useState<DetectorConfig>(defaultDetectorConfig)
    const [initialAutoStart, setInitialAutoStart] = useState(false)
    const [initialDetector, setInitialDetector] = useState<DetectorConfig>(defaultDetectorConfig)
    const [isLoading, setIsLoading] = useState(true)
    const [isSaving, setIsSaving] = useState(false)
    const [loadError, setLoadError] = useState('')

    useEffect(() => {
        let ignore = false

        const loadConfig = async () => {
            setIsLoading(true)
            setLoadError('')

            try {
                const config = await getDetectorConfig()

                if (!ignore) {
                    setAutoStart(config.auto_start)
                    setDetector(config.detector)
                    setInitialAutoStart(config.auto_start)
                    setInitialDetector(config.detector)
                }
            } catch (error) {
                const message = error instanceof Error ? error.message : 'Unable to load AI config.'

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

    const updateDetector = (patch: Partial<DetectorConfig>) => {
        setDetector((current) => ({
            ...current,
            ...patch,
        }))
    }

    const saveConfig = async () => {
        setIsSaving(true)
        const shouldNotifyRestart = hasRestartOnlyDetectorChanges(detector, initialDetector)

        try {
            const savedConfig = await updateDetectorConfig({
                auto_start: autoStart,
                detector,
            })

            setAutoStart(savedConfig.auto_start)
            setDetector(savedConfig.detector)
            setInitialAutoStart(savedConfig.auto_start)
            setInitialDetector(savedConfig.detector)
            if (shouldNotifyRestart) {
                notifyRestartRequired()
            }
            toast.success('AI config saved.')
        } catch (error) {
            toast.error(error instanceof Error ? error.message : 'Unable to save AI config.')
        } finally {
            setIsSaving(false)
        }
    }

    const cancelChanges = () => {
        setAutoStart(initialAutoStart)
        setDetector(initialDetector)
        toast.info('AI changes discarded.')
    }

    return (
        <SectionShell title="AI" className="grid gap-4 md:grid-cols-2">
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
                    {isLoading ? 'Loading AI config...' : loadError}
                </p>
            ) : null}

            <div className="grid min-w-0 gap-4 md:col-span-2 md:grid-cols-2">
                <div className="min-w-0 space-y-2">
                    <span className="text-sm font-semibold text-slate-700">Verbose</span>
                    <ToggleSwitch
                        checked={detector.verbose}
                        label={detector.verbose ? 'Enabled' : 'Disabled'}
                        onChange={(checked) => updateDetector({ verbose: checked })}
                    />
                </div>

                <div className="min-w-0 space-y-2">
                    <span className="text-sm font-semibold text-slate-700">Auto Start</span>
                    <ToggleSwitch
                        checked={autoStart}
                        label={autoStart ? 'Enabled' : 'Disabled'}
                        onChange={setAutoStart}
                    />
                </div>
            </div>

            <CustomSelect
                label="Mode"
                value={detector.mode}
                options={detectorModeOptions}
                getOptionLabel={(value) => value === 'head' ? 'Head' : 'Person'}
                onChange={(value) => updateDetector({ mode: value })}
            />

            <CustomSelect
                label="Model Size"
                value={detector.model_size}
                options={modelSizeOptions}
                onChange={(value) => updateDetector({ model_size: value })}
            />

            <CustomSelect
                label="Batch Size"
                value={detector.batch_size}
                options={batchSizeOptions}
                onChange={(value) => updateDetector({ batch_size: value })}
            />

            <NumberStepper
                label="Confidence"
                value={detector.conf}
                min={0}
                max={1}
                step={0.05}
                onChange={(value) => updateDetector({ conf: value })}
            />

            <NumberStepper
                label="VID Stride"
                value={detector.vid_stride}
                min={1}
                max={100}
                step={1}
                onChange={(value) => updateDetector({ vid_stride: value })}
            />
        </SectionShell>
    )
}

export default AIConfig
