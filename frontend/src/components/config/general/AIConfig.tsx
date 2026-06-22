import { useEffect, useState } from 'react'
import { getDetectorConfig, updateDetectorConfig } from '../../../api/detectorApi'
import { useToast } from '../../../hooks/useToast'
import { notifyRestartRequired } from '../../../lib/restartRequiredEvents'
import type { DetectionConfig } from '../../../types/config'
import { CustomSelect, NumberStepper, ToggleSwitch } from './ConfigControls'
import { batchSizeOptions, detectionTaskOptions, modelSizeOptions, trackerOptions } from './options'
import { SectionShell } from './SectionShell'

const defaultDetectionConfig: DetectionConfig = {
    task: 'pose',
    model_size: 'medium',
    batch_size: 2,
    conf: 0.5,
    tracker: 'bytetrack.yaml',
    verbose: false,
}

function hasRestartOnlyDetectionChanges(current: DetectionConfig, initial: DetectionConfig) {
    return current.task !== initial.task ||
        current.model_size !== initial.model_size ||
        current.batch_size !== initial.batch_size ||
        current.conf !== initial.conf ||
        current.tracker !== initial.tracker
}

function AIConfig() {
    const toast = useToast()
    const [autoStart, setAutoStart] = useState(false)
    const [detection, setDetection] = useState<DetectionConfig>(defaultDetectionConfig)
    const [initialAutoStart, setInitialAutoStart] = useState(false)
    const [initialDetection, setInitialDetection] = useState<DetectionConfig>(defaultDetectionConfig)
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
                    setDetection(config.detection)
                    setInitialAutoStart(config.auto_start)
                    setInitialDetection(config.detection)
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

    const updateDetection = (patch: Partial<DetectionConfig>) => {
        setDetection((current) => ({
            ...current,
            ...patch,
        }))
    }

    const saveConfig = async () => {
        setIsSaving(true)
        const shouldNotifyRestart = hasRestartOnlyDetectionChanges(detection, initialDetection)

        try {
            const savedConfig = await updateDetectorConfig({
                auto_start: autoStart,
                detection,
            })

            setAutoStart(savedConfig.auto_start)
            setDetection(savedConfig.detection)
            setInitialAutoStart(savedConfig.auto_start)
            setInitialDetection(savedConfig.detection)
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
        setDetection(initialDetection)
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
                        checked={detection.verbose}
                        label={detection.verbose ? 'Enabled' : 'Disabled'}
                        onChange={(checked) => updateDetection({ verbose: checked })}
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
                label="Task"
                value={detection.task}
                options={detectionTaskOptions}
                onChange={(value) => updateDetection({ task: value })}
            />

            <CustomSelect
                label="Model Size"
                value={detection.model_size}
                options={modelSizeOptions}
                onChange={(value) => updateDetection({ model_size: value })}
            />

            <CustomSelect
                label="Batch Size"
                value={detection.batch_size}
                options={batchSizeOptions}
                onChange={(value) => updateDetection({ batch_size: value })}
            />

            <NumberStepper
                label="Confidence"
                value={detection.conf}
                min={0}
                max={1}
                step={0.05}
                onChange={(value) => updateDetection({ conf: value })}
            />

            <CustomSelect
                label="Tracker"
                value={detection.tracker}
                options={trackerOptions}
                onChange={(value) => updateDetection({ tracker: value })}
            />
        </SectionShell>
    )
}

export default AIConfig
