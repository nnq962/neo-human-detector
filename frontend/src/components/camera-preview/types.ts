export type StreamStatus = "connecting" | "live" | "error"

export type PreviewSize = { width: number; height: number }

export type VideoSize = { width: number; height: number }

export type OverlayLayout = {
  scale: number
  offsetX: number
  offsetY: number
}
