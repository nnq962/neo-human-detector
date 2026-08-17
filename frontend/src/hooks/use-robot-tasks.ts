import { useEffect, useRef, useState } from "react"

import { notifyAuthenticationRequired } from "@/lib/auth-events"
import type { ApiResponse } from "@/api/client"
import {
  robotTasksApi,
  type RobotTaskSnapshot,
} from "@/api/robot-tasks.api"

function getWsUrl(): string {
  const protocol = window.location.protocol === "https:" ? "wss:" : "ws:"
  return `${protocol}//${window.location.host}/ws/runtime/tasks`
}

export function useRobotTasks() {
  const [snapshot, setSnapshot] = useState<RobotTaskSnapshot | null>(null)
  const [connected, setConnected] = useState(false)
  const websocketRef = useRef<WebSocket | null>(null)

  useEffect(() => {
    let disposed = false
    let retryTimer: ReturnType<typeof setTimeout> | null = null
    const abortController = new AbortController()

    robotTasksApi.getSnapshot(abortController.signal)
      .then((initialSnapshot) => {
        if (!disposed) setSnapshot(initialSnapshot)
      })
      .catch(() => {
        // WebSocket bên dưới vẫn tiếp tục kết nối nếu REST snapshot thất bại.
      })

    function connect() {
      if (disposed || websocketRef.current) return

      const websocket = new WebSocket(getWsUrl())
      websocketRef.current = websocket

      websocket.onopen = () => {
        if (disposed || websocketRef.current !== websocket) {
          websocket.close()
          return
        }
        setConnected(true)
      }

      websocket.onmessage = (event: MessageEvent) => {
        if (disposed || websocketRef.current !== websocket) return
        try {
          const response = JSON.parse(event.data) as ApiResponse<RobotTaskSnapshot>
          if (response.success) setSnapshot(response.data)
        } catch {
          // Bỏ qua payload lỗi và chờ snapshot tiếp theo.
        }
      }

      websocket.onclose = (event) => {
        if (websocketRef.current === websocket) websocketRef.current = null
        if (disposed) return
        setConnected(false)
        if (event.code === 4401) {
          notifyAuthenticationRequired()
          return
        }
        retryTimer = setTimeout(connect, 3000)
      }

      websocket.onerror = () => websocket.close()
    }

    connect()

    return () => {
      disposed = true
      abortController.abort()
      if (retryTimer) clearTimeout(retryTimer)

      const websocket = websocketRef.current
      if (websocketRef.current === websocket) websocketRef.current = null
      if (!websocket) return
      websocket.onmessage = null
      websocket.onclose = null
      websocket.onerror = null
      if (websocket.readyState === WebSocket.CONNECTING) {
        websocket.onopen = () => websocket.close()
      } else if (websocket.readyState === WebSocket.OPEN) {
        websocket.close()
      }
    }
  }, [])

  return { snapshot, connected }
}
