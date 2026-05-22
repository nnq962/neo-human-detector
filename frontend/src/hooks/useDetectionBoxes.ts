import { useEffect, useState } from 'react'
import { DETECTION_BOXES_WS_URL } from '../config/env'
import { createJsonWebSocket } from '../lib/websocket'
import type { DetectionBoxesPayload, DetectionCameraPayload } from '../types/detection'

const reconnectDelaysMs = [1000, 2000, 4000, 8000, 10000]

function isRecord(value: unknown): value is Record<string, unknown> {
    return typeof value === 'object' && value !== null
}

function isDetectionCameraPayload(value: unknown): value is DetectionCameraPayload {
    if (!isRecord(value) || !isRecord(value.resolution)) {
        return false
    }

    return (
        typeof value.timestamp === 'number' &&
        typeof value.camera_id === 'string' &&
        typeof value.camera_name === 'string' &&
        typeof value.resolution.width === 'number' &&
        typeof value.resolution.height === 'number' &&
        Array.isArray(value.objects)
    )
}

function isDetectionBoxesPayload(value: unknown): value is DetectionBoxesPayload {
    return (
        isRecord(value) &&
        isRecord(value.cameras) &&
        Object.values(value.cameras).every(isDetectionCameraPayload)
    )
}

export function useDetectionBoxes(cameraId?: string) {
    const [payload, setPayload] = useState<DetectionBoxesPayload | null>(null)

    useEffect(() => {
        if (!DETECTION_BOXES_WS_URL) {
            return undefined
        }

        let socket: WebSocket | null = null
        let reconnectTimer: number | undefined
        let reconnectAttempt = 0
        let isDisposed = false

        const clearReconnectTimer = () => {
            if (reconnectTimer !== undefined) {
                window.clearTimeout(reconnectTimer)
                reconnectTimer = undefined
            }
        }

        const scheduleReconnect = () => {
            if (isDisposed || reconnectTimer !== undefined) {
                return
            }

            const delay = reconnectDelaysMs[Math.min(reconnectAttempt, reconnectDelaysMs.length - 1)]
            reconnectAttempt += 1
            reconnectTimer = window.setTimeout(() => {
                reconnectTimer = undefined
                connect()
            }, delay)
        }

        const connect = () => {
            if (isDisposed) {
                return
            }

            socket = createJsonWebSocket<DetectionBoxesPayload>({
                url: DETECTION_BOXES_WS_URL,
                onOpen: () => {
                    reconnectAttempt = 0
                    clearReconnectTimer()
                },
                onMessage: (data) => {
                    if (isDetectionBoxesPayload(data)) {
                        setPayload(data)
                    }
                },
                onClose: scheduleReconnect,
                onError: scheduleReconnect,
            })
        }

        connect()

        return () => {
            isDisposed = true
            clearReconnectTimer()
            socket?.close()
        }
    }, [])

    if (!cameraId) {
        return null
    }

    return payload?.cameras[cameraId] ?? null
}
