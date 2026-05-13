import { useEffect, useState } from 'react'
import { DETECTION_BOXES_WS_URL } from '../config/env'
import { createJsonWebSocket } from '../lib/websocket'
import type { DetectionBoxesPayload } from '../types/detection'

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

        const socket = createJsonWebSocket<DetectionBoxesPayload>({
            url: DETECTION_BOXES_WS_URL,
            onMessage: (data) => {
                if (isDetectionBoxesPayload(data)) {
                    setPayload(data)
                }
            },
        })

        return () => {
            socket.close()
        }
    }, [])

    return payload
}
