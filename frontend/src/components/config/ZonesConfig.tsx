import { useCallback, useEffect, useState } from 'react'
import { getConfig } from '../../api/configApi'
import { CAMERA_NEO_URL } from '../../config/env'
import { useZoneRealtime } from '../../hooks/useZoneRealtime'
import type { Zone } from '../../types/config'
import type { ZoneRealtimePose } from '../../types/realtime'
import CameraPreview from '../video/CameraPreview'

type ZonesConfigProps = {
    onZonesChange?: (zones: Zone[]) => void
}

function ZonesConfig({ onZonesChange }: ZonesConfigProps) {
    const [reconnectKey, setReconnectKey] = useState(0)
    const [zones, setZones] = useState<Zone[]>([])
    const [selectedZoneIndex, setSelectedZoneIndex] = useState<number | null>(null)
    const [isEditingVertices, setIsEditingVertices] = useState(false)
    const [isAddingZone, setIsAddingZone] = useState(false)
    const [isRealtimeEnabled, setIsRealtimeEnabled] = useState(false)
    const [isLoadingZones, setIsLoadingZones] = useState(true)
    const [zonesError, setZonesError] = useState('')

    useEffect(() => {
        let ignore = false

        const loadZones = async () => {
            setIsLoadingZones(true)
            setZonesError('')

            try {
                const config = await getConfig()

                if (!ignore) {
                    setZones(config.zones)
                    setSelectedZoneIndex(null)
                }
            } catch (error) {
                if (!ignore) {
                    setZonesError(error instanceof Error ? error.message : 'Unable to load zones')
                }
            } finally {
                if (!ignore) {
                    setIsLoadingZones(false)
                }
            }
        }

        loadZones()

        return () => {
            ignore = true
        }
    }, [])

    useEffect(() => {
        if (!isLoadingZones) {
            onZonesChange?.(zones)
        }
    }, [isLoadingZones, onZonesChange, zones])

    const selectedZone = selectedZoneIndex === null ? undefined : zones[selectedZoneIndex]

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

    const updateSelectedZoneName = useCallback((name: string) => {
        if (selectedZoneIndex === null) {
            return
        }

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
    }, [selectedZoneIndex])

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

            if (nextSelectedIndex === null) {
                setIsEditingVertices(false)
            }

            return nextZones
        })
    }, [selectedZoneIndex])

    const toolButtonClass =
        'flex h-11 w-full items-center justify-center rounded-lg border border-slate-200 bg-white px-3 text-sm font-semibold text-slate-700 shadow-sm transition-colors hover:border-slate-300 hover:bg-slate-50 hover:text-slate-950 focus:outline-none focus-visible:ring-2 focus-visible:ring-sky-400 focus-visible:ring-offset-2'

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

                <button
                    type="button"
                    onClick={() => setReconnectKey((current) => current + 1)}
                    className="h-11 rounded-lg border border-slate-900 bg-slate-950 px-4 text-sm font-semibold text-white shadow-sm transition-colors hover:border-slate-800 hover:bg-slate-800 focus:outline-none focus-visible:ring-2 focus-visible:ring-slate-500 focus-visible:ring-offset-2"
                >
                    Refresh Video
                </button>
            </div>

            <div className="grid gap-6 lg:grid-cols-[minmax(240px,1fr)_minmax(0,3fr)]">
                <aside className="space-y-5">
                    <div>
                        <h3 className="mb-4 text-sm font-bold uppercase tracking-wide text-slate-500">
                            Tools
                        </h3>

                        <div className="space-y-3 rounded-xl border border-slate-100 bg-slate-50 p-4">
                            <button
                                type="button"
                                onClick={() => {
                                    setIsAddingZone((current) => !current)
                                    setIsEditingVertices(false)
                                    setSelectedZoneIndex(null)
                                    setIsRealtimeEnabled(false)
                                }}
                                className={`${toolButtonClass} ${isAddingZone
                                        ? '!border-emerald-200 !bg-emerald-50 !text-emerald-700 hover:!border-emerald-200 hover:!bg-emerald-50 hover:!text-emerald-700'
                                        : ''
                                    }`}
                            >
                                {isAddingZone ? 'Cancel Add Zone' : 'Add Zone'}
                            </button>
                            <button
                                type="button"
                                onClick={() => setIsEditingVertices((current) => !current)}
                                disabled={!selectedZone || isAddingZone}
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
                                    key={zone.name}
                                    type="button"
                                    onClick={() => {
                                        setSelectedZoneIndex(index)
                                        setIsAddingZone(false)
                                        setIsRealtimeEnabled(false)
                                    }}
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
                                    className="h-11 w-full min-w-0 rounded-lg border border-slate-200 bg-white px-3 text-sm font-medium text-slate-900 shadow-sm outline-none transition-colors placeholder:text-slate-400 hover:border-slate-300 focus:border-sky-400 focus:ring-2 focus:ring-sky-100"
                                />
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
                            src={CAMERA_NEO_URL}
                            reconnectKey={reconnectKey}
                            zones={zones}
                            selectedZoneIndex={selectedZoneIndex}
                            isEditingVertices={isEditingVertices}
                            isAddingZone={isAddingZone}
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
