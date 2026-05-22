import { useEffect, useState } from 'react'
import {
    createCamera,
    deleteCamera,
    listCameras,
    updateCamera,
    type CameraPayload,
} from '../../../api/cameraApi'
import { checkCameraWithMediaMtx } from '../../../api/mediaMtxApi'
import { useToast } from '../../../hooks/useToast'
import { notifyCameraConfigChanged } from '../../../lib/cameraEvents'
import { SectionShell } from './SectionShell'
import type { CameraConfigState } from './types'

type CameraCheckState = {
    status: 'checking'
}

type CameraActionState = {
    status: 'idle' | 'saving' | 'deleting'
}

type CameraRow = CameraConfigState & {
    localId: string
    isNew: boolean
}

type CameraConfigProps = {
    inputClass: string
    labelClass: string
}

function createEmptyCamera(): CameraRow {
    return {
        id: '',
        localId: `new_${Date.now()}_${Math.random().toString(36).slice(2, 8)}`,
        isNew: true,
        name: '',
        source: '',
        source_protocol: 'tcp',
        source_on_demand: true,
        enabled: true,
        zones: [],
    }
}

function toCameraRow(camera: CameraConfigState): CameraRow {
    return {
        ...camera,
        localId: camera.id,
        isNew: false,
        source_protocol: camera.source_protocol || 'tcp',
        source_on_demand: camera.source_on_demand ?? true,
        enabled: camera.enabled ?? true,
        zones: camera.zones || [],
    }
}

function toCameraPayload(camera: CameraRow): CameraPayload {
    return {
        name: camera.name.trim(),
        source: camera.source.trim(),
        source_protocol: camera.source_protocol || 'tcp',
        source_on_demand: camera.source_on_demand ?? true,
        enabled: camera.enabled ?? true,
        zones: camera.zones || [],
    }
}

function CameraConfig({
    inputClass,
    labelClass,
}: CameraConfigProps) {
    const toast = useToast()
    const [cameras, setCameras] = useState<CameraRow[]>([])
    const [initialCameras, setInitialCameras] = useState<CameraRow[]>([])
    const [isLoading, setIsLoading] = useState(true)
    const [loadError, setLoadError] = useState('')
    const [checkStates, setCheckStates] = useState<Record<string, CameraCheckState | undefined>>({})
    const [actionStates, setActionStates] = useState<Record<string, CameraActionState>>({})
    const [deleteConfirmKey, setDeleteConfirmKey] = useState('')

    const syncCameras = (nextCameras: CameraRow[]) => {
        setCameras(nextCameras)
    }

    const loadCameraList = async () => {
        setIsLoading(true)
        setLoadError('')

        try {
            const apiCameras = await listCameras()
            const cameraRows = apiCameras.map(toCameraRow)

            syncCameras(cameraRows)
            setInitialCameras(cameraRows)
        } catch (error) {
            const message = error instanceof Error ? error.message : 'Unable to load cameras.'

            setLoadError(message)
            toast.error(message)
        } finally {
            setIsLoading(false)
        }
    }

    useEffect(() => {
        loadCameraList()
    }, [])

    const updateCameraRow = (localId: string, patch: Partial<CameraConfigState>) => {
        syncCameras(
            cameras.map((camera) =>
                camera.localId === localId
                    ? {
                        ...camera,
                        ...patch,
                    }
                    : camera,
            ),
        )
    }

    const addCameraRow = () => {
        syncCameras([...cameras, createEmptyCamera()])
    }

    const setActionState = (localId: string, state: CameraActionState) => {
        setActionStates((current) => ({
            ...current,
            [localId]: state,
        }))
    }

    const checkCamera = async (camera: CameraRow, showToast = true) => {
        setCheckStates((current) => ({
            ...current,
            [camera.localId]: {
                status: 'checking',
            },
        }))

        try {
            const result = await checkCameraWithMediaMtx({
                source: camera.source,
                sourceProtocol: camera.source_protocol || 'tcp',
            })

            setCheckStates((current) => ({
                ...current,
                [camera.localId]: undefined,
            }))

            if (showToast) {
                if (result.ready) {
                    toast.success('Camera is ready.')
                } else {
                    toast.error('Camera stream is not ready.')
                }
            }

            return result.ready
        } catch (error) {
            const message = error instanceof Error ? error.message : 'Camera check failed.'

            setCheckStates((current) => ({
                ...current,
                [camera.localId]: undefined,
            }))

            if (showToast) {
                toast.error(message)
            }

            return false
        }
    }

    const saveCamera = async (camera: CameraRow) => {
        const payload = toCameraPayload(camera)

        if (!payload.name || !payload.source) {
            toast.error('Name and source are required.')
            return
        }

        const isCameraReady = await checkCamera(camera, false)

        if (!isCameraReady) {
            toast.error('Camera check failed. Fix the stream before saving.')
            return
        }

        setActionState(camera.localId, {
            status: 'saving',
        })

        try {
            const savedCamera = camera.isNew
                ? await createCamera(payload)
                : await updateCamera(camera.id, payload)
            const savedRow = toCameraRow(savedCamera)
            const nextCameras = camera.isNew
                ? cameras.map((current) => current.localId === camera.localId ? savedRow : current)
                : cameras.map((current) => current.localId === camera.localId ? savedRow : current)

            syncCameras(nextCameras)
            setInitialCameras((current) => {
                if (camera.isNew) {
                    return [...current, savedRow]
                }

                return current.map((initialCamera) =>
                    initialCamera.localId === camera.localId ? savedRow : initialCamera,
                )
            })
            notifyCameraConfigChanged()
            setActionStates((current) => {
                const next = { ...current }
                delete next[camera.localId]
                delete next[savedRow.localId]
                return next
            })
            toast.success('Camera saved.')
        } catch (error) {
            toast.error(error instanceof Error ? error.message : 'Unable to save camera.')
        } finally {
            setActionStates((current) => {
                const next = { ...current }
                delete next[camera.localId]
                return next
            })
        }
    }

    const removeCamera = async (camera: CameraRow) => {
        setDeleteConfirmKey('')

        if (camera.isNew) {
            syncCameras(cameras.filter((current) => current.localId !== camera.localId))
            toast.info('Unsaved camera removed.')
            return
        }

        setActionState(camera.localId, {
            status: 'deleting',
        })

        try {
            await deleteCamera(camera.id)
            syncCameras(cameras.filter((current) => current.localId !== camera.localId))
            setInitialCameras((current) =>
                current.filter((initialCamera) => initialCamera.localId !== camera.localId),
            )
            notifyCameraConfigChanged()
            toast.success('Camera deleted.')
        } catch (error) {
            toast.error(error instanceof Error ? error.message : 'Unable to delete camera.')
        } finally {
            setActionStates((current) => {
                const next = { ...current }
                delete next[camera.localId]
                return next
            })
        }
    }

    const cancelCameraChanges = (camera: CameraRow) => {
        if (camera.isNew) {
            syncCameras(cameras.filter((current) => current.localId !== camera.localId))
            toast.info('Unsaved camera removed.')
            return
        }

        const initialCamera = initialCameras.find((current) => current.localId === camera.localId)

        if (!initialCamera) {
            toast.error('Unable to restore camera.')
            return
        }

        syncCameras(
            cameras.map((current) =>
                current.localId === camera.localId ? initialCamera : current,
            ),
        )
        setDeleteConfirmKey('')
        toast.info('Camera changes discarded.')
    }

    return (
        <SectionShell title="Camera" className="space-y-4">
            <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
                <button
                    type="button"
                    onClick={addCameraRow}
                    className="h-11 rounded-lg border border-sky-200 bg-sky-50 px-4 text-sm font-semibold text-sky-700 shadow-sm transition-colors hover:border-sky-300 hover:bg-sky-100 active:bg-sky-200"
                >
                    Add Camera
                </button>
                <p className="text-sm font-medium text-slate-500">
                    {isLoading ? 'Loading cameras...' : loadError || `${cameras.length} camera(s)`}
                </p>
            </div>

            <div className="grid gap-4">
                {cameras.map((camera) => (
                    <CameraFields
                        key={camera.localId}
                        camera={camera}
                        inputClass={inputClass}
                        labelClass={labelClass}
                        checkState={checkStates[camera.localId]}
                        actionState={actionStates[camera.localId]}
                        isDeleteConfirmOpen={deleteConfirmKey === camera.localId}
                        onChange={updateCameraRow}
                        onSave={saveCamera}
                        onCheck={checkCamera}
                        onCancel={cancelCameraChanges}
                        onDelete={() => setDeleteConfirmKey(camera.localId)}
                        onCancelDelete={() => setDeleteConfirmKey('')}
                        onConfirmDelete={removeCamera}
                    />
                ))}
            </div>
        </SectionShell>
    )
}

function CameraFields({
    camera,
    inputClass,
    labelClass,
    checkState,
    actionState,
    isDeleteConfirmOpen,
    onChange,
    onSave,
    onCheck,
    onCancel,
    onDelete,
    onCancelDelete,
    onConfirmDelete,
}: {
    camera: CameraRow
    inputClass: string
    labelClass: string
    checkState?: CameraCheckState
    actionState?: CameraActionState
    isDeleteConfirmOpen: boolean
    onChange: (localId: string, patch: Partial<CameraConfigState>) => void
    onSave: (camera: CameraRow) => void
    onCheck: (camera: CameraRow) => void
    onCancel: (camera: CameraRow) => void
    onDelete: () => void
    onCancelDelete: () => void
    onConfirmDelete: (camera: CameraRow) => void
}) {
    const isChecking = checkState?.status === 'checking'
    const isSaving = actionState?.status === 'saving'
    const isDeleting = actionState?.status === 'deleting'
    const isBusy = isSaving || isDeleting

    return (
        <div className="grid gap-4 rounded-lg border border-slate-200 bg-white p-4 shadow-sm">
            <label className="min-w-0 space-y-2">
                <span className={labelClass}>Name</span>
                <input
                    type="text"
                    value={camera.name}
                    onChange={(event) => onChange(camera.localId, { name: event.target.value })}
                    className={inputClass}
                />
            </label>

            <label className="min-w-0 space-y-2">
                <span className={labelClass}>Source</span>
                <input
                    type="text"
                    value={camera.source}
                    onChange={(event) => onChange(camera.localId, { source: event.target.value })}
                    className={inputClass}
                />
            </label>

            {camera.webrtc_address ? (
                <label className="min-w-0 space-y-2">
                    <span className={labelClass}>WebRTC Address</span>
                    <input
                        type="text"
                        value={camera.webrtc_address}
                        readOnly
                        className={`${inputClass} cursor-text bg-slate-50 text-slate-600`}
                    />
                </label>
            ) : null}

            <div className="flex flex-wrap gap-3">
                <button
                    type="button"
                    onClick={() => onSave(camera)}
                    disabled={isBusy}
                    className="h-11 rounded-lg border border-emerald-200 bg-emerald-50 px-4 text-sm font-semibold text-emerald-700 shadow-sm transition-colors hover:border-emerald-300 hover:bg-emerald-100 active:bg-emerald-200 disabled:cursor-not-allowed disabled:opacity-60"
                >
                    {isSaving ? 'Saving...' : 'Save'}
                </button>

                <button
                    type="button"
                    onClick={() => onCheck(camera)}
                    disabled={isChecking || isBusy || !camera.source.trim()}
                    className="h-11 rounded-lg border border-slate-200 bg-white px-4 text-sm font-semibold text-slate-700 shadow-sm transition-colors hover:border-sky-300 hover:bg-sky-50 hover:text-sky-700 active:bg-sky-100 disabled:cursor-not-allowed disabled:opacity-60"
                >
                    {isChecking ? 'Checking...' : 'Check'}
                </button>

                <button
                    type="button"
                    onClick={() => onCancel(camera)}
                    disabled={isBusy}
                    className="h-11 rounded-lg border border-amber-200 bg-amber-50 px-4 text-sm font-semibold text-amber-700 shadow-sm transition-colors hover:border-amber-300 hover:bg-amber-100 active:bg-amber-200 disabled:cursor-not-allowed disabled:opacity-60"
                >
                    Cancel
                </button>

                <button
                    type="button"
                    onClick={onDelete}
                    disabled={isBusy}
                    className="h-11 rounded-lg border border-rose-200 bg-rose-50 px-4 text-sm font-semibold text-rose-700 shadow-sm transition-colors hover:border-rose-300 hover:bg-rose-100 active:bg-rose-200 disabled:cursor-not-allowed disabled:opacity-60"
                >
                    {isDeleting ? 'Deleting...' : 'Delete'}
                </button>
            </div>

            {isDeleteConfirmOpen ? (
                <div className="rounded-lg border border-amber-200 bg-amber-50 p-3">
                    <p className="text-sm font-semibold text-amber-800">
                        Are you sure you want to delete this camera?
                    </p>
                    <div className="mt-3 flex gap-2">
                        <button
                            type="button"
                            onClick={() => onConfirmDelete(camera)}
                            className="h-9 rounded-lg bg-rose-600 px-3 text-sm font-semibold text-white transition-colors hover:bg-rose-700 active:bg-rose-800"
                        >
                            Delete
                        </button>
                        <button
                            type="button"
                            onClick={onCancelDelete}
                            className="h-9 rounded-lg border border-slate-200 bg-white px-3 text-sm font-semibold text-slate-700 transition-colors hover:bg-slate-50 active:bg-slate-100"
                        >
                            Cancel
                        </button>
                    </div>
                </div>
            ) : null}
        </div>
    )
}

export default CameraConfig
