import type { ApiResponse } from "@/api/client"
import { notifyAuthenticationRequired } from "@/lib/auth-events"
import { publicApi } from "@/api/public.api"
import { uartApi, type RobotHeartbeatSnapshot } from "@/api/uart.api"

export interface RobotHeartbeatStreamState {
  snapshot: RobotHeartbeatSnapshot | null
  connected: boolean
}

export type RobotHeartbeatListener = (
  state: RobotHeartbeatStreamState,
) => void

interface HeartbeatStreamOptions {
  path: string
  loadSnapshot: () => Promise<RobotHeartbeatSnapshot>
  protectedAccess: boolean
}

const RETRY_DELAY_MS = 3000

function getWsUrl(path: string): string {
  const protocol = window.location.protocol === "https:" ? "wss:" : "ws:"
  return `${protocol}//${window.location.host}${path}`
}

function createHeartbeatStream(options: HeartbeatStreamOptions) {
  const listeners = new Set<RobotHeartbeatListener>()
  let websocket: WebSocket | null = null
  let retryTimer: ReturnType<typeof setTimeout> | null = null
  let initialSnapshotRequest: Promise<void> | null = null
  let currentState: RobotHeartbeatStreamState = {
    snapshot: null,
    connected: false,
  }

  const notify = (nextState: RobotHeartbeatStreamState) => {
    currentState = nextState
    listeners.forEach((listener) => listener(currentState))
  }

  const scheduleRetry = () => {
    if (retryTimer || listeners.size === 0) return
    retryTimer = setTimeout(() => {
      retryTimer = null
      connect()
    }, RETRY_DELAY_MS)
  }

  const connect = () => {
    if (websocket || listeners.size === 0) return

    const socket = new WebSocket(getWsUrl(options.path))
    websocket = socket
    socket.onopen = () => {
      if (listeners.size === 0) {
        websocket = null
        socket.close()
        return
      }
      notify({ ...currentState, connected: true })
    }
    socket.onmessage = (event: MessageEvent) => {
      try {
        const response = JSON.parse(event.data) as ApiResponse<RobotHeartbeatSnapshot>
        if (response.success) {
          notify({ snapshot: response.data, connected: true })
        }
      } catch {
        // Bỏ qua payload không đúng định dạng và chờ snapshot kế tiếp.
      }
    }
    socket.onclose = (event) => {
      if (websocket === socket) websocket = null
      notify({ ...currentState, connected: false })
      if (options.protectedAccess && event.code === 4401) {
        notifyAuthenticationRequired()
        return
      }
      scheduleRetry()
    }
    socket.onerror = () => socket.close()
  }

  const loadInitialSnapshot = () => {
    if (currentState.snapshot || initialSnapshotRequest) return

    initialSnapshotRequest = options.loadSnapshot()
      .then((snapshot) => {
        if (!currentState.snapshot) {
          notify({ ...currentState, snapshot })
        }
      })
      .catch(() => {
        // WebSocket vẫn tiếp tục kết nối nếu HTTP snapshot thất bại.
      })
      .finally(() => {
        initialSnapshotRequest = null
      })
  }

  return (listener: RobotHeartbeatListener): (() => void) => {
    listeners.add(listener)
    listener(currentState)
    loadInitialSnapshot()
    connect()

    return () => {
      listeners.delete(listener)
      if (listeners.size > 0) return

      if (retryTimer) {
        clearTimeout(retryTimer)
        retryTimer = null
      }
      const socket = websocket
      if (!socket) return

      if (socket.readyState === WebSocket.OPEN) {
        websocket = null
        socket.close()
      }
      // Socket CONNECTING tự đóng trong onopen nếu không còn subscriber.
    }
  }
}

export const subscribeRobotHeartbeats = createHeartbeatStream({
  path: "/ws/uart/robots",
  loadSnapshot: uartApi.getRobots,
  protectedAccess: true,
})

export const subscribePublicRobotHeartbeats = createHeartbeatStream({
  path: "/ws/public/uart/robots",
  loadSnapshot: publicApi.getRobots,
  protectedAccess: false,
})
