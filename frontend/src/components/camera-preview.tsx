import { useCallback, useEffect, useRef, useState } from "react"
import { Canvas, Circle, FabricText, Point, Polygon, Polyline, controlsUtils } from "fabric"
import { cn } from "@/lib/utils"
import type { Zone } from "@/api/cameras.api"
import {
  subscribeBboxes,
  type CameraDetectionPayload,
  type DetectionPayload,
  type RuntimeZonePayload,
} from "@/lib/bbox-stream"

// ── Types ────────────────────────────────────────────────────────────────────

type StreamStatus = "connecting" | "live" | "error"
type PreviewSize = { width: number; height: number }
type VideoSize = { width: number; height: number }
type OfferData = { iceUfrag: string; icePwd: string; medias: string[] }

// ── WHEP helpers ─────────────────────────────────────────────────────────────

const DOUBLE_TAP_MAX_DELAY_MS = 350
const DOUBLE_TAP_MAX_DISTANCE_PX = 28
const STREAM_RECONNECT_DELAY_MS = 3000

function getWhepUrl(src: string) {
  const t = src.trim()
  if (!t) return ""
  return t.endsWith("/whep") ? t : `${t.replace(/\/$/, "")}/whep`
}

function unquote(v: string) { return v.trim().replace(/^"|"$/g, "") }

function parseIceServers(link: string | null): RTCIceServer[] {
  if (!link) return []
  return link.split(",").map((entry) => {
    const m = entry.match(/<([^>]+)>/)
    if (!m) return null
    const s: RTCIceServer = { urls: m[1] }
    entry.split(";").forEach((p) => {
      const [k, v] = p.split("=")
      if (k?.trim() === "username") s.username = unquote(v ?? "")
      if (k?.trim() === "credential") s.credential = unquote(v ?? "")
    })
    return s
  }).filter((s): s is RTCIceServer => Boolean(s))
}

function getSessionUrl(res: Response, endpoint: string) {
  const loc = res.headers.get("location")
  return loc ? new URL(loc, endpoint).toString() : ""
}

function parseOffer(sdp: string): OfferData {
  const d: OfferData = { iceUfrag: "", icePwd: "", medias: [] }
  sdp.split("\r\n").forEach((l) => {
    if (l.startsWith("m=")) d.medias.push(l.slice(2))
    if (!d.iceUfrag && l.startsWith("a=ice-ufrag:")) d.iceUfrag = l.slice(12)
    if (!d.icePwd && l.startsWith("a=ice-pwd:")) d.icePwd = l.slice(10)
  })
  return d
}

function generateSdpFragment(offer: OfferData, candidates: RTCIceCandidate[]) {
  const byMedia = new Map<number, RTCIceCandidate[]>()
  candidates.forEach((c) => {
    if (c.sdpMLineIndex === null) return
    byMedia.set(c.sdpMLineIndex, [...(byMedia.get(c.sdpMLineIndex) ?? []), c])
  })
  let frag = `a=ice-ufrag:${offer.iceUfrag}\r\na=ice-pwd:${offer.icePwd}\r\n`
  offer.medias.forEach((media, mid) => {
    const cs = byMedia.get(mid)
    if (!cs) return
    frag += `m=${media}\r\na=mid:${mid}\r\n`
    cs.forEach((c) => { frag += `a=${c.candidate}\r\n` })
  })
  return frag
}

// ── Detection drawing constants ───────────────────────────────────────────────

const DEFAULT_BBOX_COLOR = "#7c7c7c"
const GLOBAL_ID_BBOX_COLOR = "#3784ff"

// COCO 17-keypoint skeleton connections, matching src/visualization/pose.py.
const COCO_SKELETON: [number, number, "left" | "right" | "center"][] = [
  [0, 1, "right"],
  [0, 2, "left"],
  [1, 3, "right"],
  [2, 4, "left"],
  [5, 6, "center"],
  [5, 7, "right"],
  [7, 9, "right"],
  [6, 8, "left"],
  [8, 10, "left"],
  [5, 11, "right"],
  [6, 12, "left"],
  [11, 12, "center"],
  [11, 13, "right"],
  [13, 15, "right"],
  [12, 14, "left"],
  [14, 16, "left"],
]

// nose, left/right eye, left/right ear
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

// ── Fabric helpers ────────────────────────────────────────────────────────────

const zoneColors = [
  { fill: "rgba(14, 165, 233, 0.22)", stroke: "#0ea5e9" },
  { fill: "rgba(16, 185, 129, 0.22)", stroke: "#10b981" },
  { fill: "rgba(245, 158, 11, 0.24)", stroke: "#f59e0b" },
  { fill: "rgba(244, 63, 94, 0.22)", stroke: "#f43f5e" },
  { fill: "rgba(139, 92, 246, 0.22)", stroke: "#8b5cf6" },
  { fill: "rgba(236, 72, 153, 0.22)", stroke: "#ec4899" },
]

const zoneStateColors: Record<string, { fill: string; stroke: string }> = {
  EMPTY: { fill: "rgba(239, 68, 68, 0.18)", stroke: "#ef4444" },
  PENDING_ENTER: { fill: "rgba(245, 158, 11, 0.22)", stroke: "#f59e0b" },
  OCCUPIED: { fill: "rgba(34, 197, 94, 0.22)", stroke: "#22c55e" },
  PENDING_EXIT: { fill: "rgba(234, 179, 8, 0.22)", stroke: "#eab308" },
}

function getAbsolutePolygonPoints(polygon: Polygon) {
  const transform = polygon.calcTransformMatrix()
  return polygon.points.map((p) =>
    new Point(p.x - polygon.pathOffset.x, p.y - polygon.pathOffset.y).transform(transform),
  )
}

function getZoneRuntimeState(zone: Zone, zoneStates?: Record<string, RuntimeZonePayload>) {
  if (!zoneStates) return null
  const byId = zone.id ? zoneStates[zone.id] : undefined
  return byId?.state ?? zoneStates[zone.name]?.state ?? null
}

function getZoneColor(zone: Zone, index: number, zoneStates?: Record<string, RuntimeZonePayload>) {
  const state = getZoneRuntimeState(zone, zoneStates)
  if (state && zoneStateColors[state]) return zoneStateColors[state]
  return zoneColors[index % zoneColors.length]
}

function getDetectionColor(det: DetectionPayload) {
  return det.global_id != null ? GLOBAL_ID_BBOX_COLOR : DEFAULT_BBOX_COLOR
}

// ── Detection overlay (canvas 2D thường, vẽ ngoài React render loop) ─────────

type OverlayLayout = { scale: number; offsetX: number; offsetY: number }

function computeLayout(preview: PreviewSize, video: VideoSize): OverlayLayout | null {
  if (!preview.width || !preview.height || !video.width || !video.height) return null
  const scale = Math.min(preview.width / video.width, preview.height / video.height)
  return {
    scale,
    offsetX: (preview.width - video.width * scale) / 2,
    offsetY: (preview.height - video.height * scale) / 2,
  }
}

// Khớp font mặc định của FabricText để giữ nguyên giao diện label
const DETECTION_LABEL_FONT = '11px "Times New Roman", serif'
const DETECTION_LABEL_LINE_HEIGHT = 15

function drawPoseDot(ctx: CanvasRenderingContext2D, x: number, y: number, color = POSE_KP_COLOR) {
  ctx.beginPath()
  ctx.arc(x, y, 5, 0, Math.PI * 2)
  ctx.fillStyle = color
  ctx.fill()
  ctx.lineWidth = 2
  ctx.strokeStyle = POSE_KP_BORDER
  ctx.stroke()
}

function drawPoseHipCenter(
  ctx: CanvasRenderingContext2D,
  kps: [number, number, number][],
  layout: OverlayLayout,
) {
  const leftHip = kps[11]
  const rightHip = kps[12]
  const leftOk = Boolean(leftHip && leftHip[2] >= POSE_CONF_THRESHOLD)
  const rightOk = Boolean(rightHip && rightHip[2] >= POSE_CONF_THRESHOLD)

  if (!leftOk && !rightOk) return

  let x = 0
  let y = 0
  if (leftOk && rightOk && leftHip && rightHip) {
    x = (leftHip[0] + rightHip[0]) / 2
    y = (leftHip[1] + rightHip[1]) / 2
  } else if (leftOk && leftHip) {
    x = leftHip[0]
    y = leftHip[1]
  } else if (rightHip) {
    x = rightHip[0]
    y = rightHip[1]
  }

  drawPoseDot(
    ctx,
    layout.offsetX + x * layout.scale,
    layout.offsetY + y * layout.scale,
    POSE_HIP_CENTER_COLOR,
  )
}

function drawDetections(
  ctx: CanvasRenderingContext2D,
  detections: DetectionPayload[],
  layout: OverlayLayout,
  hideFaceKeypoints: boolean,
) {
  const { scale, offsetX, offsetY } = layout

  detections.forEach((det) => {
    const color = getDetectionColor(det)
    const [x1, y1, x2, y2] = det.bbox.xyxy
    const cx1 = offsetX + x1 * scale
    const cy1 = offsetY + y1 * scale
    const cx2 = offsetX + x2 * scale
    const cy2 = offsetY + y2 * scale

    ctx.lineWidth = 2
    ctx.strokeStyle = color
    ctx.strokeRect(cx1, cy1, cx2 - cx1, cy2 - cy1)

    const lines: string[] = []
    if (det.track_id != null)
      lines.push(`#${det.track_id % 100} ${(det.confidence * 100).toFixed(0)}%`)
    if (det.global_id != null) {
      const simStr = det.similarity != null ? ` ${(det.similarity * 100).toFixed(0)}%` : ""
      lines.push(`#${det.global_id}${simStr}`)
    }
    if (det.status) lines.push(det.status)

    if (lines.length > 0) {
      ctx.font = DETECTION_LABEL_FONT
      ctx.textBaseline = "top"
      lines.forEach((line, i) => {
        const top = cy1 + 3 + i * DETECTION_LABEL_LINE_HEIGHT
        const width = ctx.measureText(line).width
        ctx.fillStyle = `${color}bb`
        ctx.fillRect(cx1 + 3, top, width + 4, DETECTION_LABEL_LINE_HEIGHT)
        ctx.fillStyle = "#ffffff"
        ctx.fillText(line, cx1 + 5, top + 2)
      })
    }

    if (det.pose) {
      const kps = det.pose.keypoints

      ctx.lineWidth = 3
      ctx.globalAlpha = 0.9
      COCO_SKELETON.forEach(([i, j, side]) => {
        if (hideFaceKeypoints && (FACE_KEYPOINT_INDICES.has(i) || FACE_KEYPOINT_INDICES.has(j))) return
        const ki = kps[i], kj = kps[j]
        if (!ki || !kj || ki[2] < POSE_CONF_THRESHOLD || kj[2] < POSE_CONF_THRESHOLD) return
        ctx.beginPath()
        ctx.moveTo(offsetX + ki[0] * scale, offsetY + ki[1] * scale)
        ctx.lineTo(offsetX + kj[0] * scale, offsetY + kj[1] * scale)
        ctx.strokeStyle = POSE_SIDE_COLORS[side]
        ctx.stroke()
      })
      ctx.globalAlpha = 1

      // ── Draw dot ─────────────────────────────────────────
      // kps.forEach(([x, y, conf], index) => {
      //   if (hideFaceKeypoints && FACE_KEYPOINT_INDICES.has(index)) return
      //   if (conf < POSE_CONF_THRESHOLD) return
      //   drawPoseDot(ctx, offsetX + x * scale, offsetY + y * scale)
      // })

      drawPoseHipCenter(ctx, kps, layout)
    }
  })
}

function zoneStatesEqual(
  a: Record<string, RuntimeZonePayload> | undefined,
  b: Record<string, RuntimeZonePayload> | undefined,
) {
  if (a === b) return true
  if (!a || !b) return false
  const aKeys = Object.keys(a)
  if (aKeys.length !== Object.keys(b).length) return false
  return aKeys.every((key) => {
    const other = b[key]
    return other != null && other.state === a[key].state && other.name === a[key].name
  })
}

// ── Props ─────────────────────────────────────────────────────────────────────

export interface CameraPreviewProps {
  src: string
  reconnectKey?: number
  zones?: Zone[]
  isAddingZone?: boolean
  isEditingVertices?: boolean
  selectedZoneIndex?: number | null
  onZoneAdd?: (points: number[][]) => void
  onZonePointsChange?: (index: number, points: number[][]) => void
  onZoneSelect?: (index: number) => void
  /** Bật overlay detection realtime cho camera này (subscribe WS dùng chung). */
  bboxCameraId?: string | null
  hideFaceKeypoints?: boolean
}

// ── Component ─────────────────────────────────────────────────────────────────

const EMPTY_ZONES: Zone[] = []

export function CameraPreview({
  src,
  reconnectKey = 0,
  zones = EMPTY_ZONES,
  isAddingZone = false,
  isEditingVertices = false,
  selectedZoneIndex = null,
  onZoneAdd,
  onZonePointsChange,
  onZoneSelect,
  bboxCameraId = null,
  hideFaceKeypoints = false,
}: CameraPreviewProps) {
  const containerRef = useRef<HTMLDivElement>(null)
  const videoRef = useRef<HTMLVideoElement>(null)
  const overlayCanvasRef = useRef<HTMLCanvasElement>(null)
  const detectionCanvasRef = useRef<HTMLCanvasElement>(null)
  const fabricCanvasRef = useRef<Canvas | null>(null)
  const isFinishingDraftRef = useRef(false)
  const draftPointsRef = useRef<number[][]>([])
  const lastDraftTapRef = useRef<{ time: number; x: number; y: number } | null>(null)

  // Dữ liệu detection tần suất cao đi qua ref + rAF, không qua setState.
  const lastDetectionsRef = useRef<DetectionPayload[] | null>(null)
  const layoutRef = useRef<OverlayLayout | null>(null)
  const rafRef = useRef<number | null>(null)
  const hideFaceKeypointsRef = useRef(hideFaceKeypoints)

  const [status, setStatus] = useState<StreamStatus>("connecting")
  const [errorMessage, setError] = useState("")
  const [resolution, setResolution] = useState("Detecting...")
  const [previewSize, setPreviewSize] = useState<PreviewSize>({ width: 0, height: 0 })
  const [videoSize, setVideoSize] = useState<VideoSize>({ width: 0, height: 0 })
  const [draftPoints, setDraftPoints] = useState<number[][]>([])
  const [zoneStates, setZoneStates] = useState<Record<string, RuntimeZonePayload> | undefined>(undefined)

  const drawDetectionFrame = useCallback(() => {
    const canvas = detectionCanvasRef.current
    const ctx = canvas?.getContext("2d")
    if (!canvas || !ctx) return
    ctx.setTransform(1, 0, 0, 1, 0, 0)
    ctx.clearRect(0, 0, canvas.width, canvas.height)
    const detections = lastDetectionsRef.current
    const layout = layoutRef.current
    if (!detections?.length || !layout) return
    const dpr = window.devicePixelRatio || 1
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0)
    drawDetections(ctx, detections, layout, hideFaceKeypointsRef.current)
  }, [])

  const scheduleDetectionDraw = useCallback(() => {
    if (rafRef.current != null) return
    rafRef.current = requestAnimationFrame(() => {
      rafRef.current = null
      drawDetectionFrame()
    })
  }, [drawDetectionFrame])

  useEffect(() => () => {
    if (rafRef.current != null) {
      cancelAnimationFrame(rafRef.current)
      // Phải reset về null: StrictMode unmount/remount giữ nguyên ref,
      // nếu còn giữ id cũ thì mọi lần schedule sau sẽ bị bỏ qua vĩnh viễn.
      rafRef.current = null
    }
  }, [])

  useEffect(() => {
    hideFaceKeypointsRef.current = hideFaceKeypoints
    scheduleDetectionDraw()
  }, [hideFaceKeypoints, scheduleDetectionDraw])

  // ── Layout + kích thước canvas detection theo preview/video size ──────────
  useEffect(() => {
    layoutRef.current = computeLayout(previewSize, videoSize)
    const canvas = detectionCanvasRef.current
    if (canvas) {
      const dpr = window.devicePixelRatio || 1
      canvas.width = Math.max(1, Math.round(previewSize.width * dpr))
      canvas.height = Math.max(1, Math.round(previewSize.height * dpr))
    }
    scheduleDetectionDraw()
  }, [previewSize, videoSize, scheduleDetectionDraw])

  // ── Subscribe luồng bbox dùng chung (chỉ khi được bật) ─────────────────────
  useEffect(() => {
    if (!bboxCameraId) return

    const applyPayload = (payload: CameraDetectionPayload | null) => {
      lastDetectionsRef.current = payload?.detections ?? null
      scheduleDetectionDraw()
      const nextZoneStates = payload?.zones
      setZoneStates((prev) => (zoneStatesEqual(prev, nextZoneStates) ? prev : nextZoneStates))
    }

    const unsubscribe = subscribeBboxes((batch) => {
      applyPayload(batch?.cameras[bboxCameraId] ?? null)
    })

    return () => {
      unsubscribe()
      applyPayload(null)
    }
  }, [bboxCameraId, scheduleDetectionDraw])

  // ── Fabric canvas init ───────────────────────────────────────────────────
  useEffect(() => {
    const el = overlayCanvasRef.current
    if (!el) return

    const canvas = new Canvas(el, { selection: false, renderOnAddRemove: false })
    canvas.defaultCursor = "default"
    canvas.hoverCursor = "default"
    Object.assign(canvas.wrapperEl.style, {
      position: "absolute", inset: "0", width: "100%", height: "100%", zIndex: "1",
      pointerEvents: "none",
    })
    canvas.upperCanvasEl.style.pointerEvents = "none"
    canvas.upperCanvasEl.style.touchAction = "none"
    fabricCanvasRef.current = canvas

    return () => { fabricCanvasRef.current = null; canvas.dispose() }
  }, [])

  // ── Preview size via ResizeObserver ──────────────────────────────────────
  useEffect(() => {
    const container = containerRef.current
    if (!container) return

    const update = () => {
      const r = container.getBoundingClientRect()
      setPreviewSize({ width: Math.round(r.width), height: Math.round(r.height) })
    }
    const ro = new ResizeObserver(update)
    update()
    ro.observe(container)
    return () => ro.disconnect()
  }, [])

  // ── Draw zones on Fabric canvas ──────────────────────────────────────────
  useEffect(() => {
    const canvas = fabricCanvasRef.current
    if (!canvas || !previewSize.width || !previewSize.height) return

    canvas.setDimensions({ width: previewSize.width, height: previewSize.height })

    const isInteractive = isEditingVertices || isAddingZone
    canvas.wrapperEl.style.pointerEvents = isInteractive ? "auto" : "none"
    canvas.upperCanvasEl.style.pointerEvents = isInteractive ? "auto" : "none"
    canvas.defaultCursor = isAddingZone ? "crosshair" : "default"
    canvas.hoverCursor = isAddingZone ? "crosshair" : isEditingVertices ? "move" : "default"
    canvas.clear()

    if (!videoSize.width || !videoSize.height) { canvas.requestRenderAll(); return }

    const scale = Math.min(previewSize.width / videoSize.width, previewSize.height / videoSize.height)
    const renderedW = videoSize.width * scale
    const renderedH = videoSize.height * scale
    const offsetX = (previewSize.width - renderedW) / 2
    const offsetY = (previewSize.height - renderedH) / 2

    zones.forEach((zone, index) => {
      const color = getZoneColor(zone, index, zoneStates)
      const isSelected = index === selectedZoneIndex
      const points = zone.points.map(([x, y]) => ({ x: offsetX + x * scale, y: offsetY + y * scale }))
      if (points.length < 3) return

      const polygon = new Polygon(points, {
        fill: color.fill,
        stroke: color.stroke,
        strokeWidth: isSelected ? 3 : 2,
        objectCaching: false,
        selectable: isEditingVertices && isSelected,
        evented: isEditingVertices,
        hasControls: isEditingVertices && isSelected,
        hasBorders: false,
        lockScalingX: true, lockScalingY: true, lockRotation: true,
        cornerColor: "#ffffff", cornerStrokeColor: color.stroke,
        cornerStyle: "circle", transparentCorners: false,
        hoverCursor: isEditingVertices && isSelected ? "move" : "default",
        moveCursor: "move",
      })

      const centroid = points.reduce((acc, p) => ({ x: acc.x + p.x / points.length, y: acc.y + p.y / points.length }), { x: 0, y: 0 })

      const label = new FabricText(zone.name, {
        left: centroid.x, top: centroid.y,
        originX: "center", originY: "center",
        fill: "#ffffff", fontSize: 13, fontWeight: "700",
        backgroundColor: color.stroke, padding: 5,
        selectable: false, evented: false,
      })

      const syncPoints = () => {
        if (!isEditingVertices || !isSelected) return
        const next = getAbsolutePolygonPoints(polygon).map((p) => [
          Math.min(Math.max(Math.round((p.x - offsetX) / scale), 0), videoSize.width),
          Math.min(Math.max(Math.round((p.y - offsetY) / scale), 0), videoSize.height),
        ])
        onZonePointsChange?.(index, next)
      }

      const updateLabel = () => {
        const abs = getAbsolutePolygonPoints(polygon)
        const c = abs.reduce((acc, p) => ({ x: acc.x + p.x / abs.length, y: acc.y + p.y / abs.length }), { x: 0, y: 0 })
        label.set({ left: c.x, top: c.y })
        label.setCoords()
        canvas.requestRenderAll()
      }

      if (isEditingVertices && isSelected) {
        polygon.controls = controlsUtils.createPolyControls(polygon, {
          cursorStyle: "crosshair",
          render: controlsUtils.renderCircleControl,
          sizeX: 12, sizeY: 12,
        })
        polygon.on("moving", updateLabel)
        polygon.on("modifyPoly", updateLabel)
        polygon.on("modified", syncPoints)
      }

      if (isEditingVertices) {
        polygon.on("mousedown", () => onZoneSelect?.(index))
      }

      canvas.add(polygon, label)
      if (isEditingVertices && isSelected) canvas.setActiveObject(polygon)
    })

    // Draft polyline when adding zone
    if (isAddingZone && draftPoints.length > 0) {
      const color = zoneColors[zones.length % zoneColors.length]
      const canvasPts = draftPoints.map(([x, y]) => ({ x: offsetX + x * scale, y: offsetY + y * scale }))

      if (canvasPts.length > 1) {
        canvas.add(new Polyline(canvasPts, {
          fill: "transparent", stroke: color.stroke, strokeWidth: 2,
          strokeDashArray: [6, 4], selectable: false, evented: false,
        }))
      }

      canvasPts.forEach((p) => {
        canvas.add(new Circle({
          left: p.x, top: p.y, radius: 5,
          fill: color.stroke, stroke: "#ffffff", strokeWidth: 2,
          originX: "center", originY: "center",
          selectable: false, evented: false,
        }))
      })
    }

    canvas.requestRenderAll()
  }, [previewSize, videoSize, zones, zoneStates, selectedZoneIndex, isEditingVertices, isAddingZone, draftPoints, onZoneSelect, onZonePointsChange])

  // ── Add zone — mouse interaction ─────────────────────────────────────────
  useEffect(() => {
    const canvas = fabricCanvasRef.current
    if (!canvas || !isAddingZone || !previewSize.width || !videoSize.width) return

    const scale = Math.min(previewSize.width / videoSize.width, previewSize.height / videoSize.height)
    const renderedW = videoSize.width * scale
    const renderedH = videoSize.height * scale
    const offsetX = (previewSize.width - renderedW) / 2
    const offsetY = (previewSize.height - renderedH) / 2

    const toImagePoint = (p: Point) => [
      Math.round((Math.min(Math.max(p.x, offsetX), offsetX + renderedW) - offsetX) / scale),
      Math.round((Math.min(Math.max(p.y, offsetY), offsetY + renderedH) - offsetY) / scale),
    ]

    const isDoubleTap = (e: MouseEvent | PointerEvent | TouchEvent, p: Point) => {
      const now = e.timeStamp || Date.now()
      const last = lastDraftTapRef.current
      if (!last) { lastDraftTapRef.current = { time: now, x: p.x, y: p.y }; return false }
      const elapsed = now - last.time
      const distance = Math.hypot(p.x - last.x, p.y - last.y)
      lastDraftTapRef.current = { time: now, x: p.x, y: p.y }
      return elapsed <= DOUBLE_TAP_MAX_DELAY_MS && distance <= DOUBLE_TAP_MAX_DISTANCE_PX
    }

    const finishDraft = () => {
      if (isFinishingDraftRef.current) return
      isFinishingDraftRef.current = true
      const pts = draftPointsRef.current
      if (pts.length < 2) { isFinishingDraftRef.current = false; return }
      draftPointsRef.current = []
      lastDraftTapRef.current = null
      setDraftPoints([])
      onZoneAdd?.(pts)
    }

    const handleMouseDown = (event: { e: MouseEvent | PointerEvent | TouchEvent }) => {
      const p = canvas.getScenePoint(event.e)
      if (event.e.detail >= 2 || isDoubleTap(event.e, p)) { finishDraft(); return }
      const next = [...draftPointsRef.current, toImagePoint(p)]
      draftPointsRef.current = next
      setDraftPoints(next)
    }

    canvas.on("mouse:down", handleMouseDown)
    return () => { canvas.off("mouse:down", handleMouseDown) }
  }, [isAddingZone, previewSize, videoSize, onZoneAdd])

  // ── Clear draft on mode exit ─────────────────────────────────────────────
  useEffect(() => {
    if (!isAddingZone) {
      draftPointsRef.current = []
      setDraftPoints([])
      isFinishingDraftRef.current = false
      lastDraftTapRef.current = null
    }
  }, [isAddingZone])

  // ── WebRTC WHEP connection ───────────────────────────────────────────────
  useEffect(() => {
    const endpointUrl = getWhepUrl(src)
    const video = videoRef.current
    if (!video) return

    if (!endpointUrl) {
      setStatus("error"); setError("Thiếu stream URL"); setResolution("Unavailable"); return
    }

    let disposed = false
    let reconnectTimer: ReturnType<typeof setTimeout> | null = null
    let cleanupConnection: (() => void) | null = null
    let attempt = 0

    const updateResolution = () => {
      const { videoWidth: w, videoHeight: h } = video
      setResolution(w > 0 && h > 0 ? `${w} × ${h}` : "Detecting...")
      setVideoSize({ width: w, height: h })
    }

    const clearReconnectTimer = () => {
      if (reconnectTimer) {
        clearTimeout(reconnectTimer)
        reconnectTimer = null
      }
    }

    const closeCurrentConnection = () => {
      const cleanup = cleanupConnection
      cleanupConnection = null
      cleanup?.()
    }

    const scheduleReconnect = (reason: string) => {
      if (disposed) return
      setStatus("error")
      setResolution("Unavailable")
      setError(`${reason}. Đang thử kết nối lại...`)
      clearReconnectTimer()
      closeCurrentConnection()
      reconnectTimer = setTimeout(() => {
        reconnectTimer = null
        connect()
      }, STREAM_RECONNECT_DELAY_MS)
    }

    const connect = async (): Promise<void> => {
      if (disposed) return

      clearReconnectTimer()
      closeCurrentConnection()

      attempt += 1
      setStatus("connecting")
      setError(attempt > 1 ? "Đang thử kết nối lại..." : "")
      setResolution("Detecting...")

      let connectionClosed = false
      let sessionUrl = ""
      let offerData: OfferData | null = null
      const queued: RTCIceCandidate[] = []
      const pc = new RTCPeerConnection()

      cleanupConnection = () => {
        connectionClosed = true
        if (sessionUrl) fetch(sessionUrl, { method: "DELETE" }).catch(() => undefined)
        pc.getSenders().forEach((s) => s.track?.stop())
        pc.getReceivers().forEach((r) => r.track?.stop())
        pc.close()
        video.pause()
        video.srcObject = null
      }

      const sendCandidates = (cs: RTCIceCandidate[]) => {
        if (!offerData || !sessionUrl || !cs.length) return
        fetch(sessionUrl, {
          method: "PATCH",
          headers: { "Content-Type": "application/trickle-ice-sdpfrag", "If-Match": "*" },
          body: generateSdpFragment(offerData, cs),
        }).catch(() => undefined)
      }

      try {
        const optRes = await fetch(endpointUrl, { method: "OPTIONS" })
        const iceServers = parseIceServers(optRes.headers.get("link"))
        if (iceServers.length) pc.setConfiguration({ iceServers })

        pc.addTransceiver("video", { direction: "recvonly" })
        pc.addTransceiver("audio", { direction: "recvonly" })
        pc.createDataChannel("")

        pc.ontrack = (e) => {
          if (!disposed && !connectionClosed) video.srcObject = e.streams[0]
        }
        pc.onconnectionstatechange = () => {
          if (disposed || connectionClosed) return
          if (pc.connectionState === "connected") {
            setStatus("live")
            setError("")
            return
          }
          if (["failed", "disconnected", "closed"].includes(pc.connectionState)) {
            scheduleReconnect(`WebRTC ${pc.connectionState}`)
          }
        }
        pc.onicecandidate = (e) => {
          if (!e.candidate) return
          if (!sessionUrl) { queued.push(e.candidate); return }
          sendCandidates([e.candidate])
        }

        const offer = await pc.createOffer()
        offerData = parseOffer(offer.sdp ?? "")
        await pc.setLocalDescription(offer)

        const response = await fetch(endpointUrl, {
          method: "POST",
          headers: { "Content-Type": "application/sdp" },
          body: offer.sdp,
        })
        if (!response.ok) throw new Error(`WHEP thất bại: HTTP ${response.status}`)

        sessionUrl = getSessionUrl(response, endpointUrl)
        await pc.setRemoteDescription({ type: "answer", sdp: await response.text() })
        sendCandidates(queued.splice(0))
        if (!disposed && !connectionClosed) await video.play()
      } catch (err) {
        if (disposed || connectionClosed) return
        scheduleReconnect(err instanceof Error ? err.message : "Không thể mở stream")
      }
    }

    video.addEventListener("loadedmetadata", updateResolution)
    video.addEventListener("resize", updateResolution)
    connect()
    return () => {
      disposed = true
      clearReconnectTimer()
      video.removeEventListener("loadedmetadata", updateResolution)
      video.removeEventListener("resize", updateResolution)
      closeCurrentConnection()
    }
  }, [src, reconnectKey])

  // ── Render ───────────────────────────────────────────────────────────────
  return (
    <div ref={containerRef} className="relative h-full w-full overflow-hidden bg-black">
      <video
        ref={videoRef}
        autoPlay muted playsInline
        className="absolute inset-0 h-full w-full object-contain"
      />

      <canvas
        ref={overlayCanvasRef}
        className="pointer-events-none absolute inset-0 z-[2] h-full w-full"
      />

      <canvas
        ref={detectionCanvasRef}
        className="pointer-events-none absolute inset-0 z-[2] h-full w-full"
      />

      {status !== "live" && (
        <div className="absolute inset-0 z-10 flex items-center justify-center bg-black/75">
          <div className="flex flex-col items-center gap-3 text-center">
            <div className="grid size-12 place-items-center rounded-full bg-white/10 text-lg font-bold text-white">
              {status === "connecting" ? "···" : "!"}
            </div>
            <p className="text-sm font-medium text-white">
              {status === "connecting" ? "Đang kết nối..." : "Không thể tải stream"}
            </p>
            {errorMessage && <p className="max-w-xs text-xs text-white/60">{errorMessage}</p>}
          </div>
        </div>
      )}

      <div className="absolute left-3 top-3 z-20 rounded-md bg-black/60 px-2.5 py-1 text-xs font-medium text-white backdrop-blur-sm">
        {resolution}
      </div>

      <div className="absolute right-3 top-3 z-20 flex items-center gap-2 rounded-md bg-black/60 px-2.5 py-1 text-xs font-medium text-white backdrop-blur-sm">
        <span className="relative flex size-2">
          {status === "live" && (
            <span className="absolute inline-flex size-full animate-ping rounded-full bg-green-400 opacity-75" />
          )}
          <span className={cn("relative inline-flex size-2 rounded-full", {
            "bg-green-400": status === "live",
            "bg-amber-400": status === "connecting",
            "bg-red-400": status === "error",
          })} />
        </span>
        {status === "live" ? "Live" : status === "connecting" ? "Connecting" : "Error"}
      </div>
    </div>
  )
}
