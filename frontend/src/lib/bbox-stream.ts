// Singleton WebSocket stream cho bbox runtime. Mỗi namespace public/private có
// một kết nối dùng chung, parse message một lần rồi fan-out qua callback.

import { notifyAuthenticationRequired } from "@/lib/auth-events"

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

export interface BboxStreamState {
  batch: BboxesBatch | null
  connected: boolean
}

export type BboxListener = (batch: BboxesBatch | null) => void
export type BboxStateListener = (state: BboxStreamState) => void

const RETRY_DELAY_MS = 3000

function getWsUrl(path: string): string {
  const protocol = window.location.protocol === "https:" ? "wss:" : "ws:"
  return `${protocol}//${window.location.host}${path}`
}

function createBboxStream(path: string, protectedAccess: boolean) {
  const listeners = new Set<BboxStateListener>()
  let websocket: WebSocket | null = null
  let retryTimer: ReturnType<typeof setTimeout> | null = null
  let currentState: BboxStreamState = { batch: null, connected: false }

  const notify = (state: BboxStreamState) => {
    currentState = state
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
    const socket = new WebSocket(getWsUrl(path))
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
        const batch = JSON.parse(event.data) as BboxesBatch
        if (batch.cameras) notify({ batch, connected: true })
      } catch {
        // Bỏ qua payload hỏng và chờ message tiếp theo.
      }
    }
    socket.onclose = (event) => {
      if (websocket === socket) websocket = null
      notify({ batch: null, connected: false })
      if (protectedAccess && event.code === 4401) {
        notifyAuthenticationRequired()
        return
      }
      scheduleRetry()
    }
    socket.onerror = () => socket.close()
  }

  const subscribeState = (listener: BboxStateListener): (() => void) => {
    listeners.add(listener)
    listener(currentState)
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
    }
  }

  const subscribeBatch = (listener: BboxListener): (() => void) =>
    subscribeState((state) => listener(state.batch))

  return { subscribeBatch, subscribeState }
}

const privateStream = createBboxStream("/ws/runtime/bboxes", true)
const publicStream = createBboxStream("/ws/public/runtime/bboxes", false)

export const subscribeBboxes = privateStream.subscribeBatch
export const subscribeBboxState = privateStream.subscribeState
export const subscribePublicBboxes = publicStream.subscribeBatch
export const subscribePublicBboxState = publicStream.subscribeState
