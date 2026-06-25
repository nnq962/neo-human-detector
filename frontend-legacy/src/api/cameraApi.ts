import { apiRequest } from '../lib/http'
import type { Camera } from '../types/config'

export type CameraPayload = {
    name: string
    stream: Camera['stream']
    enabled?: boolean
    zones?: Camera['zones']
}

export type CameraUpdatePayload = Partial<CameraPayload>

export function listCameras() {
    return apiRequest<Camera[]>('/api/cameras')
}

export function getCamera(cameraId: string) {
    return apiRequest<Camera>(`/api/cameras/${encodeURIComponent(cameraId)}`)
}

export function createCamera(camera: CameraPayload) {
    return apiRequest<Camera>('/api/cameras', {
        method: 'POST',
        body: JSON.stringify(camera),
    })
}

export function replaceCamera(cameraId: string, camera: CameraPayload) {
    return apiRequest<Camera>(`/api/cameras/${encodeURIComponent(cameraId)}`, {
        method: 'PUT',
        body: JSON.stringify(camera),
    })
}

export function updateCamera(cameraId: string, camera: CameraUpdatePayload) {
    return apiRequest<Camera>(`/api/cameras/${encodeURIComponent(cameraId)}`, {
        method: 'PATCH',
        body: JSON.stringify(camera),
    })
}

export function deleteCamera(cameraId: string) {
    return apiRequest<void>(`/api/cameras/${encodeURIComponent(cameraId)}`, {
        method: 'DELETE',
    })
}
