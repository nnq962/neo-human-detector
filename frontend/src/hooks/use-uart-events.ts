import { useCallback, useEffect, useRef, useState } from "react"
import { getUartEventsWsUrl, type UartEvent } from "@/api/uart.api"

export type UartEventsStatus = "disconnected" | "connecting" | "connected" | "error"

interface UseUartEventsOptions {
  enabled?: boolean
  type?: UartEvent["type"]
  prefix?: string
  onEvent?: (event: UartEvent) => void
  onRawMessage?: (message: string) => void
}

function buildUartEventsWsUrl(options: UseUartEventsOptions) {
  const url = new URL(getUartEventsWsUrl())

  if (options.type) {
    url.searchParams.set("type", options.type)
  }

  if (options.prefix) {
    url.searchParams.set("prefix", options.prefix)
  }

  return url.toString()
}

export function useUartEvents(options: UseUartEventsOptions = {}) {
  const [status, setStatus] = useState<UartEventsStatus>("disconnected")
  const wsRef = useRef<WebSocket | null>(null)
  const optionsRef = useRef(options)

  useEffect(() => {
    optionsRef.current = options
  }, [options])

  const disconnect = useCallback(() => {
    wsRef.current?.close()
    wsRef.current = null
    setStatus("disconnected")
  }, [])

  const connect = useCallback(() => {
    if (wsRef.current) return

    setStatus("connecting")
    const ws = new WebSocket(buildUartEventsWsUrl(optionsRef.current))
    wsRef.current = ws

    ws.onopen = () => {
      setStatus("connected")
    }

    ws.onmessage = (event) => {
      try {
        const payload = JSON.parse(event.data) as UartEvent
        optionsRef.current.onEvent?.(payload)
      } catch {
        optionsRef.current.onRawMessage?.(String(event.data))
      }
    }

    ws.onerror = () => {
      setStatus("error")
    }

    ws.onclose = () => {
      if (wsRef.current === ws) {
        wsRef.current = null
      }

      setStatus("disconnected")
    }
  }, [])

  useEffect(() => {
    if (!options.enabled) return

    connect()
    return disconnect
  }, [connect, disconnect, options.enabled])

  useEffect(() => {
    return () => {
      wsRef.current?.close()
    }
  }, [])

  return {
    status,
    connect,
    disconnect,
  }
}
