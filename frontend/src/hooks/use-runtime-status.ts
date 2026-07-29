import { useEffect, useRef, useState } from "react"
import type { ApiResponse } from "@/api/client"
import type { RuntimeStatus } from "@/api/runtime.api"

function getWsUrl(): string {
  const protocol = window.location.protocol === "https:" ? "wss:" : "ws:"
  return `${protocol}//${window.location.host}/ws/runtime/status`
}

export function useRuntimeStatus() {
  const [status, setStatus] = useState<RuntimeStatus | null>(null)
  const [connected, setConnected] = useState(false)
  const wsRef = useRef<WebSocket | null>(null)
  const retryRef = useRef<ReturnType<typeof setTimeout> | null>(null)

  useEffect(() => {
    let disposed = false

    function connect() {
      if (disposed) return
      const ws = new WebSocket(getWsUrl())
      wsRef.current = ws

      ws.onopen = () => {
        if (disposed) {
          ws.close()
          return
        }
        setConnected(true)
      }

      ws.onmessage = (e: MessageEvent) => {
        try {
          const msg = JSON.parse(e.data) as ApiResponse<RuntimeStatus>
          if (msg.success) setStatus(msg.data)
        } catch {
          // Bỏ qua message không đúng định dạng response của API.
        }
      }

      ws.onclose = () => {
        if (wsRef.current === ws) {
          wsRef.current = null
        }
        setConnected(false)
        if (!disposed) {
          retryRef.current = setTimeout(connect, 3000)
        }
      }

      ws.onerror = () => ws.close()
    }

    connect()

    return () => {
      disposed = true
      if (retryRef.current) clearTimeout(retryRef.current)

      const ws = wsRef.current
      if (!ws) return

      ws.onmessage = null
      ws.onclose = null
      ws.onerror = null
      if (ws.readyState === WebSocket.CONNECTING) {
        ws.onopen = () => ws.close()
      } else if (ws.readyState === WebSocket.OPEN) {
        ws.close()
      }
    }
  }, [])

  return { status, connected }
}
