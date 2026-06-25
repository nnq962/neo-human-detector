import { apiRequest } from '../lib/http'
import type { DetectionConfig, DetectorSettings } from '../types/config'

export interface DetectorStatus {
    is_running: boolean
    model_path?: string | null
    task?: string | null
    conf?: number | null
    batch_size?: number | null
    verbose?: boolean | null
    cameras?: Array<{
        id: string
        name: string
        source: string
        zones: number
    }>
}

export interface DetectorCommandResponse {
    status: string
    message: string
}

export type DetectionConfigUpdatePayload = Partial<DetectionConfig>

export type DetectorSettingsUpdatePayload = {
    auto_start?: boolean
    detection?: DetectionConfigUpdatePayload
}

export function getDetectorConfig() {
    return apiRequest<DetectorSettings>('/api/detector/config')
}

export function updateDetectorConfig(settings: DetectorSettingsUpdatePayload) {
    return apiRequest<DetectorSettings>('/api/detector/config', {
        method: 'PATCH',
        body: JSON.stringify(settings),
    })
}

export function replaceDetectorConfig(settings: DetectorSettings) {
    return apiRequest<DetectorSettings>('/api/detector/config', {
        method: 'PUT',
        body: JSON.stringify(settings),
    })
}

export function getDetectorStatus() {
    return apiRequest<DetectorStatus>('/api/detector/status')
}

export function startDetector() {
    return apiRequest<DetectorCommandResponse>('/api/detector/start', {
        method: 'POST',
    })
}

export function stopDetector() {
    return apiRequest<DetectorCommandResponse>('/api/detector/stop', {
        method: 'POST',
    })
}

export function restartDetector() {
    return apiRequest<DetectorCommandResponse>('/api/detector/restart', {
        method: 'POST',
    })
}
