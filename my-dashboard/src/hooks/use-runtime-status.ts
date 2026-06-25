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
  const stoppedRef = useRef(false)
  const wsRef = useRef<WebSocket | null>(null)
  const retryRef = useRef<ReturnType<typeof setTimeout> | null>(null)

  useEffect(() => {
    stoppedRef.current = false

    function connect() {
      if (stoppedRef.current) return
      const ws = new WebSocket(getWsUrl())
      wsRef.current = ws

      ws.onopen = () => {
        if (stoppedRef.current) { ws.close(); return }
        setConnected(true)
      }

      ws.onmessage = (e: MessageEvent) => {
        try {
          const msg = JSON.parse(e.data) as ApiResponse<RuntimeStatus>
          if (msg.success) setStatus(msg.data)
        } catch {}
      }

      ws.onclose = () => {
        setConnected(false)
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
  }, [])

  return { status, connected }
}
