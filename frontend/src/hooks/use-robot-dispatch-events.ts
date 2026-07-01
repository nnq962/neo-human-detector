import { useEffect, useRef, useState } from "react"
import {
  getRobotDispatchEventsWsUrl,
  type RobotDispatchEvent,
} from "@/api/robot-dispatch.api"

export type RobotDispatchEventsStatus = "connecting" | "connected" | "disconnected"

interface UseRobotDispatchEventsOptions {
  maxEvents?: number
}

export function useRobotDispatchEvents(options: UseRobotDispatchEventsOptions = {}) {
  const maxEvents = options.maxEvents ?? 100
  const [events, setEvents] = useState<RobotDispatchEvent[]>([])
  const [status, setStatus] = useState<RobotDispatchEventsStatus>("connecting")
  const stoppedRef = useRef(false)
  const wsRef = useRef<WebSocket | null>(null)
  const retryRef = useRef<ReturnType<typeof setTimeout> | null>(null)

  useEffect(() => {
    stoppedRef.current = false

    function connect() {
      if (stoppedRef.current) return

      setStatus("connecting")
      const ws = new WebSocket(getRobotDispatchEventsWsUrl())
      wsRef.current = ws

      ws.onopen = () => {
        if (stoppedRef.current) {
          ws.close()
          return
        }
        setStatus("connected")
      }

      ws.onmessage = (e: MessageEvent) => {
        try {
          const event = JSON.parse(e.data) as RobotDispatchEvent
          setEvents((current) => {
            const bySequence = new Map<number, RobotDispatchEvent>()

            for (const item of current) {
              bySequence.set(item.sequence, item)
            }
            bySequence.set(event.sequence, event)

            return [...bySequence.values()]
              .sort((a, b) => b.sequence - a.sequence)
              .slice(0, maxEvents)
          })
        } catch {}
      }

      ws.onclose = () => {
        if (wsRef.current === ws) {
          wsRef.current = null
        }
        setStatus("disconnected")

        if (!stoppedRef.current) {
          retryRef.current = setTimeout(connect, 3000)
        }
      }

      ws.onerror = () => ws.close()
    }

    connect()

    return () => {
      stoppedRef.current = true
      if (retryRef.current) clearTimeout(retryRef.current)
      wsRef.current?.close()
    }
  }, [maxEvents])

  return { events, status }
}
