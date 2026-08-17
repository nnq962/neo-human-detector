import {
  useCallback,
  useEffect,
  useRef,
  type Dispatch,
  type SetStateAction,
} from "react"
import {
  subscribeBboxes,
  subscribePublicBboxes,
  type CameraDetectionPayload,
  type DetectionPayload,
  type RuntimeZonePayload,
} from "@/lib/bbox-stream"
import { computeLayout } from "./layout"
import type { OverlayLayout, PreviewSize, VideoSize } from "./types"

const DEFAULT_BBOX_COLOR = "#7c7c7c"
const GLOBAL_ID_BBOX_COLOR = "#3784ff"
const FACE_KEYPOINT_INDICES = new Set([0, 1, 2, 3, 4])
const POSE_CONF_THRESHOLD = 0.3
const POSE_SIDE_COLORS = {
  left: "#32c800",
  right: "#0050ff",
  center: "#dcdc00",
}
const POSE_KP_COLOR = "#ffffff"
const POSE_KP_BORDER = "#1e1e1e"
const POSE_HIP_CENTER_COLOR = "#ff0000"
const DETECTION_LABEL_FONT = '11px "Times New Roman", serif'
const DETECTION_LABEL_LINE_HEIGHT = 15
const HUD_BBOX_BORDER_COLOR = "rgba(224, 242, 254, 0.82)"
const HUD_BBOX_GRID_COLOR = "rgba(224, 242, 254, 0.28)"
const HUD_BBOX_CORNER_COLOR = "#f8fdff"

const COCO_SKELETON: [number, number, "left" | "right" | "center"][] = [
  [0, 1, "right"], [0, 2, "left"], [1, 3, "right"], [2, 4, "left"],
  [5, 6, "center"], [5, 7, "right"], [7, 9, "right"], [6, 8, "left"],
  [8, 10, "left"], [5, 11, "right"], [6, 12, "left"], [11, 12, "center"],
  [11, 13, "right"], [13, 15, "right"], [12, 14, "left"], [14, 16, "left"],
]

function getDetectionColor(detection: DetectionPayload) {
  return detection.global_id != null ? GLOBAL_ID_BBOX_COLOR : DEFAULT_BBOX_COLOR
}

function drawPoseDot(
  context: CanvasRenderingContext2D,
  x: number,
  y: number,
  color = POSE_KP_COLOR,
) {
  context.beginPath()
  context.arc(x, y, 5, 0, Math.PI * 2)
  context.fillStyle = color
  context.fill()
  context.lineWidth = 2
  context.strokeStyle = POSE_KP_BORDER
  context.stroke()
}

function drawPoseHipCenter(
  context: CanvasRenderingContext2D,
  keypoints: [number, number, number][],
  layout: OverlayLayout,
) {
  const leftHip = keypoints[11]
  const rightHip = keypoints[12]
  const leftVisible = Boolean(leftHip && leftHip[2] >= POSE_CONF_THRESHOLD)
  const rightVisible = Boolean(rightHip && rightHip[2] >= POSE_CONF_THRESHOLD)
  if (!leftVisible && !rightVisible) return

  let x = 0
  let y = 0
  if (leftVisible && rightVisible && leftHip && rightHip) {
    x = (leftHip[0] + rightHip[0]) / 2
    y = (leftHip[1] + rightHip[1]) / 2
  } else if (leftVisible && leftHip) {
    ;[x, y] = leftHip
  } else if (rightHip) {
    ;[x, y] = rightHip
  }

  drawPoseDot(
    context,
    layout.offsetX + x * layout.scale,
    layout.offsetY + y * layout.scale,
    POSE_HIP_CENTER_COLOR,
  )
}

function drawHudBoundingBox(
  context: CanvasRenderingContext2D,
  x: number,
  y: number,
  width: number,
  height: number,
) {
  if (width <= 0 || height <= 0) return

  const shortestSide = Math.min(width, height)
  const gridSpacing = Math.max(18, Math.min(34, shortestSide / 6))
  const cornerLength = Math.max(11, Math.min(30, shortestSide * 0.13))
  const cornerInset = 1.5

  context.save()

  context.beginPath()
  context.rect(x, y, width, height)
  context.clip()

  const background = context.createLinearGradient(x, y, x, y + height)
  background.addColorStop(0, "rgba(56, 189, 248, 0.19)")
  background.addColorStop(1, "rgba(3, 105, 161, 0.27)")
  context.fillStyle = background
  context.fillRect(x, y, width, height)

  context.beginPath()
  for (let gridX = x + gridSpacing; gridX < x + width; gridX += gridSpacing) {
    context.moveTo(gridX, y)
    context.lineTo(gridX, y + height)
  }
  for (let gridY = y + gridSpacing; gridY < y + height; gridY += gridSpacing) {
    context.moveTo(x, gridY)
    context.lineTo(x + width, gridY)
  }
  context.lineWidth = 1
  context.strokeStyle = HUD_BBOX_GRID_COLOR
  context.stroke()
  context.restore()

  context.save()
  context.lineWidth = 1.5
  context.strokeStyle = HUD_BBOX_BORDER_COLOR
  context.strokeRect(x, y, width, height)

  context.beginPath()
  context.moveTo(x + cornerLength, y + cornerInset)
  context.lineTo(x + cornerInset, y + cornerInset)
  context.lineTo(x + cornerInset, y + cornerLength)

  context.moveTo(x + width - cornerLength, y + cornerInset)
  context.lineTo(x + width - cornerInset, y + cornerInset)
  context.lineTo(x + width - cornerInset, y + cornerLength)

  context.moveTo(x + cornerInset, y + height - cornerLength)
  context.lineTo(x + cornerInset, y + height - cornerInset)
  context.lineTo(x + cornerLength, y + height - cornerInset)

  context.moveTo(x + width - cornerLength, y + height - cornerInset)
  context.lineTo(x + width - cornerInset, y + height - cornerInset)
  context.lineTo(x + width - cornerInset, y + height - cornerLength)

  context.lineWidth = 4
  context.lineCap = "square"
  context.lineJoin = "miter"
  context.strokeStyle = HUD_BBOX_CORNER_COLOR
  context.shadowColor = "rgba(186, 230, 253, 0.75)"
  context.shadowBlur = 6
  context.stroke()
  context.restore()
}

function drawDetections(
  context: CanvasRenderingContext2D,
  detections: DetectionPayload[],
  layout: OverlayLayout,
  hideFaceKeypoints: boolean,
) {
  const { scale, offsetX, offsetY } = layout

  detections.forEach((detection) => {
    const color = getDetectionColor(detection)
    const [x1, y1, x2, y2] = detection.bbox.xyxy
    const canvasX1 = offsetX + x1 * scale
    const canvasY1 = offsetY + y1 * scale
    const canvasX2 = offsetX + x2 * scale
    const canvasY2 = offsetY + y2 * scale

    drawHudBoundingBox(
      context,
      canvasX1,
      canvasY1,
      canvasX2 - canvasX1,
      canvasY2 - canvasY1,
    )

    const labels: string[] = []
    if (detection.track_id != null) {
      labels.push(`#${detection.track_id % 100} ${(detection.confidence * 100).toFixed(0)}%`)
    }
    if (detection.global_id != null) {
      const similarity = detection.similarity != null
        ? ` ${(detection.similarity * 100).toFixed(0)}%`
        : ""
      labels.push(`#${detection.global_id}${similarity}`)
    }
    if (detection.status) labels.push(detection.status)

    context.font = DETECTION_LABEL_FONT
    context.textBaseline = "top"
    labels.forEach((label, index) => {
      const top = canvasY1 + 3 + index * DETECTION_LABEL_LINE_HEIGHT
      const width = context.measureText(label).width
      context.fillStyle = `${color}bb`
      context.fillRect(canvasX1 + 3, top, width + 4, DETECTION_LABEL_LINE_HEIGHT)
      context.fillStyle = "#ffffff"
      context.fillText(label, canvasX1 + 5, top + 2)
    })

    if (!detection.pose) return
    const keypoints = detection.pose.keypoints
    context.lineWidth = 3
    context.globalAlpha = 0.9
    COCO_SKELETON.forEach(([startIndex, endIndex, side]) => {
      if (
        hideFaceKeypoints
        && (FACE_KEYPOINT_INDICES.has(startIndex) || FACE_KEYPOINT_INDICES.has(endIndex))
      ) return

      const start = keypoints[startIndex]
      const end = keypoints[endIndex]
      if (!start || !end || start[2] < POSE_CONF_THRESHOLD || end[2] < POSE_CONF_THRESHOLD) return
      context.beginPath()
      context.moveTo(offsetX + start[0] * scale, offsetY + start[1] * scale)
      context.lineTo(offsetX + end[0] * scale, offsetY + end[1] * scale)
      context.strokeStyle = POSE_SIDE_COLORS[side]
      context.stroke()
    })
    context.globalAlpha = 1
    drawPoseHipCenter(context, keypoints, layout)
  })
}

function zoneStatesEqual(
  current: Record<string, RuntimeZonePayload> | undefined,
  next: Record<string, RuntimeZonePayload> | undefined,
) {
  if (current === next) return true
  if (!current || !next) return false
  const keys = Object.keys(current)
  if (keys.length !== Object.keys(next).length) return false
  return keys.every((key) => {
    const other = next[key]
    return other != null
      && other.state === current[key].state
      && other.name === current[key].name
  })
}

interface DetectionOverlayProps {
  cameraId: string | null
  previewSize: PreviewSize
  videoSize: VideoSize
  hideFaceKeypoints: boolean
  publicAccess?: boolean
  onZoneStatesChange: Dispatch<
    SetStateAction<Record<string, RuntimeZonePayload> | undefined>
  >
}

export function DetectionOverlay({
  cameraId,
  previewSize,
  videoSize,
  hideFaceKeypoints,
  publicAccess = false,
  onZoneStatesChange,
}: DetectionOverlayProps) {
  const canvasRef = useRef<HTMLCanvasElement>(null)
  const detectionsRef = useRef<DetectionPayload[] | null>(null)
  const layoutRef = useRef<OverlayLayout | null>(null)
  const animationFrameRef = useRef<number | null>(null)
  const hideFaceKeypointsRef = useRef(hideFaceKeypoints)

  const drawFrame = useCallback(() => {
    const canvas = canvasRef.current
    const context = canvas?.getContext("2d")
    if (!canvas || !context) return

    context.setTransform(1, 0, 0, 1, 0, 0)
    context.clearRect(0, 0, canvas.width, canvas.height)
    const detections = detectionsRef.current
    const layout = layoutRef.current
    if (!detections?.length || !layout) return

    const pixelRatio = window.devicePixelRatio || 1
    context.setTransform(pixelRatio, 0, 0, pixelRatio, 0, 0)
    drawDetections(context, detections, layout, hideFaceKeypointsRef.current)
  }, [])

  const scheduleDraw = useCallback(() => {
    if (animationFrameRef.current != null) return
    animationFrameRef.current = requestAnimationFrame(() => {
      animationFrameRef.current = null
      drawFrame()
    })
  }, [drawFrame])

  useEffect(() => () => {
    if (animationFrameRef.current != null) {
      cancelAnimationFrame(animationFrameRef.current)
      animationFrameRef.current = null
    }
  }, [])

  useEffect(() => {
    hideFaceKeypointsRef.current = hideFaceKeypoints
    scheduleDraw()
  }, [hideFaceKeypoints, scheduleDraw])

  useEffect(() => {
    layoutRef.current = computeLayout(previewSize, videoSize)
    const canvas = canvasRef.current
    if (canvas) {
      const pixelRatio = window.devicePixelRatio || 1
      canvas.width = Math.max(1, Math.round(previewSize.width * pixelRatio))
      canvas.height = Math.max(1, Math.round(previewSize.height * pixelRatio))
    }
    scheduleDraw()
  }, [previewSize, videoSize, scheduleDraw])

  useEffect(() => {
    if (!cameraId) {
      detectionsRef.current = null
      onZoneStatesChange(undefined)
      scheduleDraw()
      return
    }

    const applyPayload = (payload: CameraDetectionPayload | null) => {
      detectionsRef.current = payload?.detections ?? null
      scheduleDraw()
      const nextStates = payload?.zones
      onZoneStatesChange((current) =>
        zoneStatesEqual(current, nextStates) ? current : nextStates,
      )
    }

    const subscribe = publicAccess ? subscribePublicBboxes : subscribeBboxes
    const unsubscribe = subscribe((batch) => {
      applyPayload(batch?.cameras[cameraId] ?? null)
    })
    return () => {
      unsubscribe()
      detectionsRef.current = null
      onZoneStatesChange(undefined)
      scheduleDraw()
    }
  }, [cameraId, onZoneStatesChange, publicAccess, scheduleDraw])

  return (
    <canvas
      ref={canvasRef}
      className="pointer-events-none absolute inset-0 z-[2] h-full w-full"
    />
  )
}
