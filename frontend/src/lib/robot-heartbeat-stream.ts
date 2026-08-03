import type { ApiResponse } from "@/api/client"
import { uartApi, type RobotHeartbeatSnapshot } from "@/api/uart.api"

export interface RobotHeartbeatStreamState {
  snapshot: RobotHeartbeatSnapshot | null
  connected: boolean
}

export type RobotHeartbeatListener = (
  state: RobotHeartbeatStreamState,
) => void

const RETRY_DELAY_MS = 3000
const listeners = new Set<RobotHeartbeatListener>()

let websocket: WebSocket | null = null
let retryTimer: ReturnType<typeof setTimeout> | null = null
let initialSnapshotRequest: Promise<void> | null = null
let currentState: RobotHeartbeatStreamState = {
  snapshot: null,
  connected: false,
}

function getWsUrl(): string {
  const protocol = window.location.protocol === "https:" ? "wss:" : "ws:"
  return `${protocol}//${window.location.host}/ws/uart/robots`
}

function notify(nextState: RobotHeartbeatStreamState) {
  currentState = nextState
  listeners.forEach((listener) => listener(currentState))
}

function scheduleRetry() {
  if (retryTimer || listeners.size === 0) return
  retryTimer = setTimeout(() => {
    retryTimer = null
    connect()
  }, RETRY_DELAY_MS)
}

function connect() {
  if (websocket || listeners.size === 0) return

  const socket = new WebSocket(getWsUrl())
  websocket = socket
  socket.onopen = () => {
    if (listeners.size === 0) {
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
  socket.onclose = () => {
    if (websocket === socket) websocket = null
    notify({ ...currentState, connected: false })
    scheduleRetry()
  }
  socket.onerror = () => socket.close()
}

function loadInitialSnapshot() {
  if (currentState.snapshot || initialSnapshotRequest) return

  initialSnapshotRequest = uartApi.getRobots()
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

export function subscribeRobotHeartbeats(
  listener: RobotHeartbeatListener,
): () => void {
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
    // Không đóng socket khi còn CONNECTING. onopen sẽ tự đóng nếu lúc đó
    // vẫn không có subscriber, tránh cảnh báo của trình duyệt trong StrictMode.
  }
}
