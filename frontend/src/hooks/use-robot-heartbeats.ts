import { useEffect, useRef, useState } from "react"

import type { ApiResponse } from "@/api/client"
import { uartApi, type RobotHeartbeatSnapshot } from "@/api/uart.api"


function getWsUrl(): string {
  const protocol = window.location.protocol === "https:" ? "wss:" : "ws:"
  return `${protocol}//${window.location.host}/ws/uart/robots`
}


export function useRobotHeartbeats() {
  const [snapshot, setSnapshot] = useState<RobotHeartbeatSnapshot | null>(null)
  const [connected, setConnected] = useState(false)
  const stoppedRef = useRef(false)
  const websocketRef = useRef<WebSocket | null>(null)
  const retryRef = useRef<ReturnType<typeof setTimeout> | null>(null)

  useEffect(() => {
    stoppedRef.current = false

    uartApi.getRobots()
      .then((initialSnapshot) => {
        if (!stoppedRef.current) setSnapshot(initialSnapshot)
      })
      .catch(() => {
        // WebSocket bên dưới vẫn tiếp tục kết nối nếu HTTP snapshot thất bại.
      })

    function connect() {
      if (stoppedRef.current) return

      const websocket = new WebSocket(getWsUrl())
      websocketRef.current = websocket

      websocket.onopen = () => {
        if (stoppedRef.current) {
          websocket.close()
          return
        }
        setConnected(true)
      }

      websocket.onmessage = (event: MessageEvent) => {
        try {
          const response = JSON.parse(event.data) as ApiResponse<RobotHeartbeatSnapshot>
          if (response.success) setSnapshot(response.data)
        } catch {
          // Bỏ qua payload không đúng format và chờ snapshot kế tiếp.
        }
      }

      websocket.onclose = () => {
        setConnected(false)
        if (!stoppedRef.current) {
          retryRef.current = setTimeout(connect, 3000)
        }
      }

      websocket.onerror = () => websocket.close()
    }

    connect()

    return () => {
      stoppedRef.current = true
      if (retryRef.current) clearTimeout(retryRef.current)
      websocketRef.current?.close()
    }
  }, [])

  return { snapshot, connected }
}
