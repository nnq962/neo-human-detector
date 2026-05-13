import { apiRequest } from '../lib/http'

export interface DetectorStatus {
    is_running: boolean
    source: string
    model_path: string
    conf: number
    vid_stride: number
    verbose: boolean
}

export interface DetectorCommandResponse {
    status: string
    message: string
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
