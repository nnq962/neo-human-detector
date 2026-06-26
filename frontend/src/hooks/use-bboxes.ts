import { useEffect, useRef, useState } from "react"

export interface BBoxCoords {
  xyxy: [number, number, number, number]
  xywh_norm: [number, number, number, number]
}

export interface PoseData {
  keypoints: [number, number, number][]
  keypoints_norm: [number, number, number][]
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

interface BboxesPayload {
  timestamp: number
  sequence: number
  cameras: Record<string, CameraDetectionPayload>
}

function getWsUrl(): string {
  const protocol = window.location.protocol === "https:" ? "wss:" : "ws:"
  return `${protocol}//${window.location.host}/ws/runtime/bboxes`
}

export function useBboxes() {
  const [cameras, setCameras] = useState<Record<string, CameraDetectionPayload>>({})
  const stoppedRef = useRef(false)
  const wsRef = useRef<WebSocket | null>(null)
  const retryRef = useRef<ReturnType<typeof setTimeout> | null>(null)

  useEffect(() => {
    stoppedRef.current = false

    function connect() {
      if (stoppedRef.current) return
      const ws = new WebSocket(getWsUrl())
      wsRef.current = ws

      ws.onmessage = (e: MessageEvent) => {
        try {
          const msg = JSON.parse(e.data) as BboxesPayload
          if (msg.cameras) {
            setCameras(msg.cameras)
          }
        } catch {}
      }

      ws.onclose = () => {
        setCameras({})
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

  return cameras
}
