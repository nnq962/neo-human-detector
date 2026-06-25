import { useEffect, useState } from 'react'
import { ZONE_REALTIME_WS_URL } from '../config/env'
import { createJsonWebSocket } from '../lib/websocket'
import type { ZoneRealtimePose } from '../types/realtime'

type ZoneRealtimeStatus = 'idle' | 'connecting' | 'connected' | 'error'

function isZoneRealtimePose(value: ZoneRealtimePose) {
    return (
        typeof value.x === 'number' &&
        typeof value.y === 'number' &&
        typeof value.theta === 'number'
    )
}

export function useZoneRealtime(enabled: boolean, onPose: (pose: ZoneRealtimePose) => void) {
    const [status, setStatus] = useState<ZoneRealtimeStatus>('idle')

    useEffect(() => {
        if (!enabled) {
            setStatus('idle')
            return undefined
        }

        if (!ZONE_REALTIME_WS_URL) {
            setStatus('error')
            return undefined
        }

        setStatus('connecting')

        const socket = createJsonWebSocket<ZoneRealtimePose>({
            url: ZONE_REALTIME_WS_URL,
            onOpen: () => setStatus('connected'),
            onClose: () => setStatus((current) => (current === 'idle' ? current : 'idle')),
            onError: () => setStatus('error'),
            onMessage: (pose) => {
                if (isZoneRealtimePose(pose)) {
                    onPose(pose)
                }
            },
        })

        return () => {
            setStatus('idle')
            socket.close()
        }
    }, [enabled, onPose])

    return status
}
