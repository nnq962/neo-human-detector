import { useEffect, useState } from 'react'
import { DETECTION_BOXES_WS_URL } from '../config/env'
import { createJsonWebSocket } from '../lib/websocket'
import type { DetectionBoxesPayload } from '../types/detection'

const reconnectDelaysMs = [1000, 2000, 4000, 8000, 10000]

function isDetectionBoxesPayload(value: DetectionBoxesPayload) {
    return (
        typeof value.timestamp === 'number' &&
        typeof value.resolution?.width === 'number' &&
        typeof value.resolution?.height === 'number' &&
        Array.isArray(value.objects)
    )
}

export function useDetectionBoxes() {
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

    return payload
}
