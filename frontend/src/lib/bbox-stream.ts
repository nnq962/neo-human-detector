// Singleton WebSocket stream cho /ws/runtime/bboxes.
// Một kết nối dùng chung cho mọi subscriber: parse message đúng một lần rồi
// fan-out qua callback, không đi qua React state để tránh re-render 20 lần/giây.

export interface BBoxCoords {
  xyxy: [number, number, number, number]
}

export interface PoseData {
  keypoints: [number, number, number][]
}

export interface DetectionPayload {
  index: number
  confidence: number
  class_id: number
  track_id: number | null
  global_id: number | null
  similarity: number | null
  status: string | null
  zone: string | null
  bbox: BBoxCoords
  pose: PoseData | null
}

export type RuntimeZoneState = "EMPTY" | "PENDING_ENTER" | "OCCUPIED" | "PENDING_EXIT"

export interface RuntimeZonePayload {
  id: string | null
  name: string
  state: RuntimeZoneState | string
}

export interface CameraDetectionPayload {
  camera_id: string
  camera_name: string
  timestamp: number
  frame_index: number
  resolution: { width: number; height: number }
  zones: Record<string, RuntimeZonePayload>
  detections: DetectionPayload[]
}

export interface BboxesBatch {
  timestamp: number
  sequence: number
  cameras: Record<string, CameraDetectionPayload>
}

// Batch null nghĩa là mất kết nối — subscriber nên xóa overlay hiện tại.
export type BboxListener = (batch: BboxesBatch | null) => void

const RETRY_DELAY_MS = 3000

const listeners = new Set<BboxListener>()
let ws: WebSocket | null = null
let retryTimer: ReturnType<typeof setTimeout> | null = null

function getWsUrl(): string {
  const protocol = window.location.protocol === "https:" ? "wss:" : "ws:"
  return `${protocol}//${window.location.host}/ws/runtime/bboxes`
}

function notify(batch: BboxesBatch | null) {
  listeners.forEach((listener) => listener(batch))
}

function scheduleRetry() {
  if (retryTimer || listeners.size === 0) return
  retryTimer = setTimeout(() => {
    retryTimer = null
    connect()
  }, RETRY_DELAY_MS)
}

function connect() {
  if (ws || listeners.size === 0) return
  const socket = new WebSocket(getWsUrl())
  ws = socket

  socket.onmessage = (e: MessageEvent) => {
    try {
      const msg = JSON.parse(e.data) as BboxesBatch
      if (msg.cameras) notify(msg)
    } catch {
      // bỏ qua message hỏng
    }
  }

  socket.onclose = () => {
    if (ws === socket) ws = null
    notify(null)
    scheduleRetry()
  }

  socket.onerror = () => socket.close()
}

export function subscribeBboxes(listener: BboxListener): () => void {
  listeners.add(listener)
  connect()

  return () => {
    listeners.delete(listener)
    if (listeners.size === 0) {
      if (retryTimer) {
        clearTimeout(retryTimer)
        retryTimer = null
      }
      const socket = ws
      ws = null
      socket?.close()
    }
  }
}
