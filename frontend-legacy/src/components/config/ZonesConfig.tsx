import { useCallback, useEffect, useState } from 'react'
import { listCameras, updateCamera } from '../../api/cameraApi'
import { useZoneRealtime } from '../../hooks/useZoneRealtime'
import { useToast } from '../../hooks/useToast'
import { subscribeCameraConfigChanged } from '../../lib/cameraEvents'
import { notifyRestartRequired } from '../../lib/restartRequiredEvents'
import type { Camera, Zone } from '../../types/config'
import type { ZoneRealtimePose } from '../../types/realtime'
import { CustomSelect } from './general/ConfigControls'
import CameraPreview from '../video/CameraPreview'

type ZonesConfigProps = {
    reloadKey?: number
}

function cloneZones(zones: Zone[]) {
    return zones.map((zone) => ({
        ...zone,
        goal_pose: { ...zone.goal_pose },
        points: zone.points.map((point) => [...point]),
    }))
}

function isDuplicateZoneName(zones: Zone[], selectedIndex: number, name: string) {
    const normalizedName = name.trim()

    if (!normalizedName) {
        return false
    }

    return zones.some((zone, index) => index !== selectedIndex && zone.name.trim() === normalizedName)
}

function isCameraEnabled(camera: Camera) {
    return camera.enabled ?? true
}

function ZonesConfig({ reloadKey = 0 }: ZonesConfigProps) {
    const toast = useToast()
    const [reconnectKey, setReconnectKey] = useState(0)
    const [cameraReloadKey, setCameraReloadKey] = useState(0)
    const [cameras, setCameras] = useState<Camera[]>([])
    const [selectedCameraId, setSelectedCameraId] = useState('')
    const [zones, setZones] = useState<Zone[]>([])
    const [initialZones, setInitialZones] = useState<Zone[]>([])
    const [detectionZones, setDetectionZones] = useState<Zone[]>([])
    const [selectedZoneIndex, setSelectedZoneIndex] = useState<number | null>(null)
    const [isEditingVertices, setIsEditingVertices] = useState(false)
    const [isAddingZone, setIsAddingZone] = useState(false)
    const [isRealtimeEnabled, setIsRealtimeEnabled] = useState(false)
    const [isLoadingZones, setIsLoadingZones] = useState(true)
    const [isSavingZones, setIsSavingZones] = useState(false)
    const [zonesError, setZonesError] = useState('')
    const [zoneNameError, setZoneNameError] = useState('')

    useEffect(() => {
        let ignore = false

        const loadCameras = async () => {
            setIsLoadingZones(true)
            setZonesError('')
            setIsEditingVertices(false)
            setIsAddingZone(false)
            setIsRealtimeEnabled(false)
            setSelectedZoneIndex(null)
            setZoneNameError('')

            try {
                const apiCameras = await listCameras()
                const enabledCameras = apiCameras.filter(isCameraEnabled)
                const selectedCamera = enabledCameras.find((camera) => camera.id === selectedCameraId)
                    || enabledCameras[0]
                const nextZones = cloneZones(selectedCamera?.zones || [])

                if (!ignore) {
                    setCameras(enabledCameras)
                    setSelectedCameraId(selectedCamera?.id || '')
                    setZones(nextZones)
                    setInitialZones(cloneZones(nextZones))
                    setDetectionZones(cloneZones(nextZones))
                }
            } catch (error) {
                if (!ignore) {
                    setZonesError(error instanceof Error ? error.message : 'Unable to load cameras')
                }
            } finally {
                if (!ignore) {
                    setIsLoadingZones(false)
                }
            }
        }

        loadCameras()

        return () => {
            ignore = true
        }
    }, [cameraReloadKey, reloadKey, selectedCameraId])

    useEffect(() => {
        return subscribeCameraConfigChanged(() => {
            setCameraReloadKey((current) => current + 1)
            setReconnectKey((current) => current + 1)
        })
    }, [])

    const selectedCamera = cameras.find((camera) => camera.id === selectedCameraId)
    const selectedZone = selectedZoneIndex === null ? undefined : zones[selectedZoneIndex]
    const videoSrc = selectedCamera?.webrtc_address || ''

    const selectCamera = useCallback((cameraId: string) => {
        const nextCamera = cameras.find((camera) => camera.id === cameraId)
        const nextZones = cloneZones(nextCamera?.zones || [])

        setSelectedCameraId(cameraId)
        setZones(nextZones)
        setInitialZones(cloneZones(nextZones))
        setDetectionZones(cloneZones(nextZones))
        setSelectedZoneIndex(null)
        setIsEditingVertices(false)
        setIsAddingZone(false)
        setIsRealtimeEnabled(false)
        setZoneNameError('')
        setReconnectKey((current) => current + 1)
    }, [cameras])

    const updateSelectedZonePoseFromRealtime = useCallback((pose: ZoneRealtimePose) => {
        if (selectedZoneIndex === null) {
            return
        }

        setZones((currentZones) =>
            currentZones.map((zone, index) =>
                index === selectedZoneIndex
                    ? {
                        ...zone,
                        goal_pose: pose,
                    }
                    : zone,
            ),
        )
    }, [selectedZoneIndex])

    const realtimeStatus = useZoneRealtime(
        Boolean(isRealtimeEnabled && selectedZone),
        updateSelectedZonePoseFromRealtime,
    )
    const realtimeDotClass =
        realtimeStatus === 'connected'
            ? 'bg-emerald-500'
            : realtimeStatus === 'connecting'
                ? 'bg-amber-400'
                : realtimeStatus === 'error'
                    ? 'bg-rose-500'
                    : 'bg-slate-300'

    const updateZonePoints = useCallback((zoneIndex: number, points: number[][]) => {
        setZones((currentZones) =>
            currentZones.map((zone, index) =>
                index === zoneIndex
                    ? {
                        ...zone,
                        points,
                    }
                    : zone,
            ),
        )
    }, [])

    const selectZone = useCallback((zoneIndex: number) => {
        setSelectedZoneIndex(zoneIndex)
        setIsAddingZone(false)
        setIsRealtimeEnabled(false)
        setZoneNameError('')
    }, [])

    const toggleVertexEditing = useCallback(() => {
        setIsEditingVertices((current) => {
            if (current) {
                return false
            }

            if (selectedZoneIndex === null && zones.length > 0) {
                setSelectedZoneIndex(0)
            }

            return true
        })
    }, [selectedZoneIndex, zones.length])

    const updateSelectedZoneName = useCallback((name: string) => {
        if (selectedZoneIndex === null) {
            return
        }

        if (isDuplicateZoneName(zones, selectedZoneIndex, name)) {
            setZoneNameError(`Zone name "${name.trim()}" already exists.`)
            return
        }

        setZoneNameError('')
        setZones((currentZones) =>
            currentZones.map((zone, index) =>
                index === selectedZoneIndex
                    ? {
                        ...zone,
                        name,
                    }
                    : zone,
            ),
        )
    }, [selectedZoneIndex, zones])

    const updateSelectedZoneGoalPose = useCallback((
        field: 'x' | 'y' | 'theta',
        value: string,
    ) => {
        if (selectedZoneIndex === null || isRealtimeEnabled) {
            return
        }

        const parsedValue = Number(value)

        setZones((currentZones) =>
            currentZones.map((zone, index) =>
                index === selectedZoneIndex
                    ? {
                        ...zone,
                        goal_pose: {
                            ...zone.goal_pose,
                            [field]: Number.isNaN(parsedValue) ? 0 : parsedValue,
                        },
                    }
                    : zone,
            ),
        )
    }, [isRealtimeEnabled, selectedZoneIndex])

    const addZone = useCallback((points: number[][]) => {
        setZones((currentZones) => {
            const nextZoneIndex = currentZones.length
            const nextZones = [
                ...currentZones,
                {
                    name: `zone_${nextZoneIndex + 1}`,
                    goal_pose: {
                        x: 0,
                        y: 0,
                        theta: 0,
                    },
                    points,
                },
            ]

            setSelectedZoneIndex(nextZoneIndex)
            setIsAddingZone(false)
            setIsEditingVertices(true)
            setIsRealtimeEnabled(false)
            setZoneNameError('')

            return nextZones
        })
    }, [])

    const deleteSelectedZone = useCallback(() => {
        if (selectedZoneIndex === null) {
            return
        }

        setZones((currentZones) => {
            const nextZones = currentZones.filter((_, index) => index !== selectedZoneIndex)
            const nextSelectedIndex =
                nextZones.length === 0 ? null : Math.min(selectedZoneIndex, nextZones.length - 1)

            setSelectedZoneIndex(nextSelectedIndex)
            setIsRealtimeEnabled(false)
            setZoneNameError('')

            if (nextSelectedIndex === null) {
                setIsEditingVertices(false)
            }

            return nextZones
        })
    }, [selectedZoneIndex])

    const saveZones = async () => {
        if (!selectedCameraId) {
            toast.error('Select a camera before saving zones.')
            return
        }

        if (zoneNameError) {
            toast.error('Fix zone name errors before saving.')
            return
        }

        setIsSavingZones(true)

        try {
            const savedCamera = await updateCamera(selectedCameraId, {
                zones,
            })
            const savedZones = cloneZones(savedCamera.zones || [])

            setCameras((currentCameras) =>
                currentCameras.map((camera) =>
                    camera.id === savedCamera.id ? savedCamera : camera,
                ),
            )
            setZones(savedZones)
            setInitialZones(cloneZones(savedZones))
            setDetectionZones(cloneZones(savedZones))
            notifyRestartRequired()
            toast.success('Zones saved.')
        } catch (error) {
            toast.error(error instanceof Error ? error.message : 'Unable to save zones.')
        } finally {
            setIsSavingZones(false)
        }
    }

    const cancelZoneChanges = () => {
        const nextZones = cloneZones(initialZones)

        setZones(nextZones)
        setDetectionZones(cloneZones(nextZones))
        setSelectedZoneIndex(null)
        setIsEditingVertices(false)
        setIsAddingZone(false)
        setIsRealtimeEnabled(false)
        setZoneNameError('')
        toast.info('Zone changes discarded.')
    }

    const toolButtonClass =
        'flex h-11 w-full items-center justify-center rounded-lg border border-slate-200 bg-white px-3 text-sm font-semibold text-slate-700 shadow-sm transition-colors hover:border-slate-300 hover:bg-slate-50 hover:text-slate-950 focus:outline-none focus-visible:ring-2 focus-visible:ring-sky-400 focus-visible:ring-offset-2'

    const saveButtonClass =
        'h-11 flex-1 rounded-lg border border-emerald-200 bg-emerald-50 px-3 text-sm font-semibold text-emerald-700 shadow-sm transition-colors hover:border-emerald-300 hover:bg-emerald-100 active:bg-emerald-200 disabled:cursor-not-allowed disabled:opacity-60'
    const cancelButtonClass =
        'h-11 flex-1 rounded-lg border border-amber-200 bg-amber-50 px-3 text-sm font-semibold text-amber-700 shadow-sm transition-colors hover:border-amber-300 hover:bg-amber-100 active:bg-amber-200 disabled:cursor-not-allowed disabled:opacity-60'

    return (
        <section className="rounded-xl border border-slate-200 bg-white p-4 shadow-[0_12px_36px_rgba(15,23,42,0.08)] sm:p-6">
            <div className="mb-6 flex flex-col gap-3 border-b border-slate-100 pb-5 sm:flex-row sm:items-center sm:justify-between">
                <div>
                    <h2 className="text-lg font-bold text-slate-950">Zones Config</h2>
                    <p className="mt-1 text-sm text-slate-500">
                        {isLoadingZones
                            ? 'Loading zones...'
                            : zonesError || `${zones.length} zones loaded`}
                    </p>
                </div>

                <div className="flex w-full flex-col gap-3 sm:w-auto sm:flex-row sm:items-center">
                    <div className="min-w-0 sm:w-56">
                        <CustomSelect
                            value={selectedCameraId}
                            options={cameras.map((camera) => camera.id)}
                            disabled={isLoadingZones || cameras.length === 0}
                            placeholder="No cameras"
                            getOptionLabel={(cameraId) =>
                                cameras.find((camera) => camera.id === cameraId)?.name || cameraId
                            }
                            onChange={selectCamera}
                        />
                    </div>

                    <button
                        type="button"
                        onClick={() => setReconnectKey((current) => current + 1)}
                        className="h-11 rounded-lg border border-slate-900 bg-slate-950 px-4 text-sm font-semibold text-white shadow-sm transition-colors hover:border-slate-800 hover:bg-slate-800 focus:outline-none focus-visible:ring-2 focus-visible:ring-slate-500 focus-visible:ring-offset-2"
                    >
                        Refresh Video
                    </button>
                </div>
            </div>

            <div className="grid gap-6 lg:grid-cols-[minmax(240px,1fr)_minmax(0,3fr)]">
                <aside className="space-y-5">
                    <div>
                        <h3 className="mb-4 text-sm font-bold uppercase tracking-wide text-slate-500">
                            Tools
                        </h3>

                        <div className="space-y-3 rounded-xl border border-slate-100 bg-slate-50 p-4">
                            <div className="flex gap-3">
                                <button
                                    type="button"
                                    onClick={saveZones}
                                    disabled={isSavingZones || isLoadingZones || !selectedCameraId}
                                    className={saveButtonClass}
                                >
                                    {isSavingZones ? 'Saving...' : 'Save'}
                                </button>
                                <button
                                    type="button"
                                    onClick={cancelZoneChanges}
                                    disabled={isSavingZones || isLoadingZones || !selectedCameraId}
                                    className={cancelButtonClass}
                                >
                                    Cancel
                                </button>
                            </div>

                            <button
                                type="button"
                                onClick={() => {
                                    setIsAddingZone((current) => !current)
                                    setIsEditingVertices(false)
                                    setSelectedZoneIndex(null)
                                    setIsRealtimeEnabled(false)
                                }}
                                className={`${toolButtonClass} ${isAddingZone
                                        ? '!border-red-200 !bg-red-50 !text-red-700 hover:!border-red-200 hover:!bg-red-50 hover:!text-red-700'
                                        : ''
                                    }`}
                            >
                                {isAddingZone ? 'Cancel Add Zone' : 'Add Zone'}
                            </button>
                            <button
                                type="button"
                                onClick={toggleVertexEditing}
                                disabled={zones.length === 0 || isAddingZone}
                                className={`${toolButtonClass} ${isEditingVertices
                                        ? '!border-sky-200 !bg-sky-50 !text-sky-700 hover:!border-sky-200 hover:!bg-sky-50 hover:!text-sky-700'
                                        : ''
                                    } disabled:cursor-not-allowed disabled:opacity-50`}
                            >
                                {isEditingVertices ? 'Done Editing' : 'Edit Vertices'}
                            </button>
                            <button
                                type="button"
                                onClick={deleteSelectedZone}
                                disabled={!selectedZone || isAddingZone}
                                className={`${toolButtonClass} disabled:cursor-not-allowed disabled:opacity-50`}
                            >
                                Delete Zone
                            </button>
                        </div>
                    </div>

                    <div>
                        <h3 className="mb-4 text-sm font-bold uppercase tracking-wide text-slate-500">
                            Zone List
                        </h3>

                        <div className="space-y-2 rounded-xl border border-slate-100 bg-slate-50 p-3">
                            {zones.length === 0 ? (
                                <div className="rounded-lg border border-dashed border-slate-200 bg-white px-3 py-6 text-center text-sm font-medium text-slate-500">
                                    {isLoadingZones ? 'Loading zones...' : 'No zones available'}
                                </div>
                            ) : null}

                            {zones.map((zone, index) => (
                                <button
                                    key={`${zone.name}-${index}`}
                                    type="button"
                                    onClick={() => selectZone(index)}
                                    className={`flex h-12 w-full items-center justify-between gap-3 rounded-lg border px-3 text-left text-sm font-semibold shadow-sm transition-colors ${selectedZoneIndex === index
                                            ? 'border-sky-200 bg-sky-50 text-sky-700'
                                            : 'border-slate-200 bg-white text-slate-700 hover:border-slate-300 hover:text-slate-950'
                                        }`}
                                >
                                    <span className="truncate">{zone.name}</span>
                                    <span className="shrink-0 rounded-md bg-white px-2 py-1 text-xs font-bold text-slate-500 shadow-sm">
                                        {zone.points.length} points
                                    </span>
                                </button>
                            ))}
                        </div>
                    </div>

                    <div>
                        <h3 className="mb-4 text-sm font-bold uppercase tracking-wide text-slate-500">
                            Selected Zone
                        </h3>

                        <div className="space-y-4 rounded-xl border border-slate-100 bg-slate-50 p-4">
                            <label className="flex h-11 items-center justify-between gap-4 rounded-lg border border-slate-200 bg-white px-3 shadow-sm transition-colors hover:border-slate-300">
                                <span className="flex min-w-0 items-center gap-2 text-sm font-semibold text-slate-800">
                                    Realtime Data
                                    {isRealtimeEnabled ? (
                                        <span className="relative grid size-3 place-items-center">
                                            <span className={`absolute size-2 rounded-full ${realtimeDotClass} opacity-75 animate-ping`} />
                                            <span className={`relative size-2 rounded-full ${realtimeDotClass}`} />
                                        </span>
                                    ) : null}
                                </span>
                                <input
                                    type="checkbox"
                                    checked={isRealtimeEnabled}
                                    disabled={!selectedZone}
                                    onChange={(event) => setIsRealtimeEnabled(event.target.checked)}
                                    className="peer sr-only"
                                />
                                <span className="relative h-7 w-12 rounded-full bg-slate-200 transition-colors after:absolute after:left-1 after:top-1 after:size-5 after:rounded-full after:bg-white after:shadow-sm after:transition-transform peer-checked:bg-emerald-500 peer-checked:after:translate-x-5 peer-focus-visible:ring-2 peer-focus-visible:ring-emerald-500 peer-focus-visible:ring-offset-2 peer-disabled:cursor-not-allowed peer-disabled:opacity-50" />
                            </label>

                            <label className="block space-y-2">
                                <span className="text-sm font-semibold text-slate-700">Name</span>
                                <input
                                    type="text"
                                    value={selectedZone?.name ?? ''}
                                    disabled={!selectedZone}
                                    onChange={(event) => updateSelectedZoneName(event.target.value)}
                                    aria-invalid={zoneNameError ? 'true' : 'false'}
                                    className={`h-11 w-full min-w-0 rounded-lg border bg-white px-3 text-sm font-medium text-slate-900 shadow-sm outline-none transition-colors placeholder:text-slate-400 hover:border-slate-300 focus:ring-2 ${zoneNameError
                                            ? 'border-rose-300 focus:border-rose-400 focus:ring-rose-100'
                                            : 'border-slate-200 focus:border-sky-400 focus:ring-sky-100'
                                        }`}
                                />
                                {zoneNameError ? (
                                    <p className="text-xs font-semibold text-rose-600">{zoneNameError}</p>
                                ) : null}
                            </label>

                            <div className="grid gap-3 sm:grid-cols-3 lg:grid-cols-1 xl:grid-cols-3">
                                {['X', 'Y', 'Theta'].map((label) => (
                                    <label key={label} className="block space-y-2">
                                        <span className="text-sm font-semibold text-slate-700">{label}</span>
                                        <input
                                            type="number"
                                            value={
                                                label === 'X'
                                                    ? selectedZone?.goal_pose.x ?? ''
                                                    : label === 'Y'
                                                        ? selectedZone?.goal_pose.y ?? ''
                                                        : selectedZone?.goal_pose.theta ?? ''
                                            }
                                            disabled={!selectedZone || isRealtimeEnabled}
                                            onChange={(event) =>
                                                updateSelectedZoneGoalPose(
                                                    label === 'X' ? 'x' : label === 'Y' ? 'y' : 'theta',
                                                    event.target.value,
                                                )
                                            }
                                            className="h-11 w-full min-w-0 rounded-lg border border-slate-200 bg-white px-3 text-sm font-medium text-slate-900 shadow-sm outline-none transition-colors hover:border-slate-300 focus:border-sky-400 focus:ring-2 focus:ring-sky-100 disabled:cursor-not-allowed disabled:bg-slate-100 disabled:text-slate-500 [appearance:textfield] [&::-webkit-inner-spin-button]:appearance-none [&::-webkit-outer-spin-button]:appearance-none"
                                        />
                                    </label>
                                ))}
                            </div>
                        </div>
                    </div>
                </aside>

                <div>
                    <h3 className="mb-4 text-sm font-bold uppercase tracking-wide text-slate-500">
                        Video Preview
                    </h3>

                    <div className="overflow-hidden rounded-xl border border-slate-100 bg-slate-50 p-4">
                        <CameraPreview
                            cameraId={selectedCamera?.id}
                            src={videoSrc}
                            reconnectKey={reconnectKey}
                            zones={zones}
                            detectionZones={detectionZones}
                            selectedZoneIndex={selectedZoneIndex}
                            showZonesOverlay={isEditingVertices}
                            isEditingVertices={isEditingVertices}
                            isAddingZone={isAddingZone}
                            onZoneSelect={selectZone}
                            onZonePointsChange={updateZonePoints}
                            onZoneAdd={addZone}
                        />
                    </div>
                </div>
            </div>
        </section>
    )
}

export default ZonesConfig
