import { useEffect, useRef, useState } from "react"
import {
  Canvas,
  Circle,
  FabricText,
  Group,
  Path,
  Point,
  Polygon,
  Polyline,
  Rect,
  controlsUtils,
} from "fabric"
import type { Zone } from "@/api/cameras.api"
import type { RuntimeZonePayload } from "@/lib/bbox-stream"
import type { PreviewSize, VideoSize } from "./types"

const DOUBLE_TAP_MAX_DELAY_MS = 350
const DOUBLE_TAP_MAX_DISTANCE_PX = 28
const MIN_FABRIC_PIXEL_RATIO = 2

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


interface ZoneOverlayProps {
  zones: Zone[]
  zoneStates?: Record<string, RuntimeZonePayload>
  previewSize: PreviewSize
  videoSize: VideoSize
  isAddingZone: boolean
  isEditingVertices: boolean
  isPickingServicePoint: boolean
  selectedZoneIndex: number | null
  servicePoint: [number, number] | null
  onZoneAdd?: (points: number[][]) => void
  onZonePointsChange?: (index: number, points: number[][]) => void
  onZoneSelect?: (index: number) => void
  onServicePointChange?: (point: [number, number]) => void
}

export function ZoneOverlay({
  zones,
  zoneStates,
  previewSize,
  videoSize,
  isAddingZone,
  isEditingVertices,
  isPickingServicePoint,
  selectedZoneIndex,
  servicePoint,
  onZoneAdd,
  onZonePointsChange,
  onZoneSelect,
  onServicePointChange,
}: ZoneOverlayProps) {
  const overlayHostRef = useRef<HTMLDivElement>(null)
  const fabricCanvasRef = useRef<Canvas | null>(null)
  const isFinishingDraftRef = useRef(false)
  const draftPointsRef = useRef<number[][]>([])
  const lastDraftTapRef = useRef<{ time: number; x: number; y: number } | null>(null)
  const [draftPoints, setDraftPoints] = useState<number[][]>([])

  // ── Fabric canvas init ───────────────────────────────────────────────────
  useEffect(() => {
    const host = overlayHostRef.current
    if (!host) return

    const element = document.createElement("canvas")
    host.appendChild(element)

    const canvas = new Canvas(element, {
      selection: false,
      renderOnAddRemove: false,
      enableRetinaScaling: true,
    })
    canvas.getRetinaScaling = () => Math.max(
      window.devicePixelRatio || 1,
      MIN_FABRIC_PIXEL_RATIO,
    )
    canvas.defaultCursor = "default"
    canvas.hoverCursor = "default"
    Object.assign(canvas.wrapperEl.style, {
      position: "absolute", inset: "0", width: "100%", height: "100%", zIndex: "1",
      pointerEvents: "none",
    })
    canvas.upperCanvasEl.style.pointerEvents = "none"
    canvas.upperCanvasEl.style.touchAction = "none"
    fabricCanvasRef.current = canvas

    return () => {
      fabricCanvasRef.current = null
      canvas.dispose()
      host.replaceChildren()
    }
  }, [])

  // ── Draw zones on Fabric canvas ──────────────────────────────────────────
  useEffect(() => {
    const canvas = fabricCanvasRef.current
    if (!canvas || !previewSize.width || !previewSize.height) return

    canvas.setDimensions({ width: previewSize.width, height: previewSize.height })

    const isInteractive = isEditingVertices || isAddingZone || isPickingServicePoint
    const isPickingPoint = isPickingServicePoint && selectedZoneIndex !== null
    canvas.wrapperEl.style.pointerEvents = isInteractive ? "auto" : "none"
    canvas.upperCanvasEl.style.pointerEvents = isInteractive ? "auto" : "none"
    canvas.defaultCursor = isAddingZone || isPickingPoint ? "crosshair" : "default"
    canvas.hoverCursor = isAddingZone || isPickingPoint
      ? "crosshair"
      : isEditingVertices ? "move" : "default"
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
        selectable: isEditingVertices && isSelected && !isPickingPoint,
        evented: isEditingVertices && !isPickingPoint,
        hasControls: isEditingVertices && isSelected && !isPickingPoint,
        hasBorders: false,
        lockScalingX: true, lockScalingY: true, lockRotation: true,
        cornerColor: "#ffffff", cornerStrokeColor: color.stroke,
        cornerStyle: "circle", transparentCorners: false,
        hoverCursor: isEditingVertices && isSelected && !isPickingPoint ? "move" : "default",
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

      if (isEditingVertices && isSelected && !isPickingPoint) {
        polygon.controls = controlsUtils.createPolyControls(polygon, {
          cursorStyle: "crosshair",
          render: controlsUtils.renderCircleControl,
          sizeX: 12, sizeY: 12,
        })
        polygon.on("moving", updateLabel)
        polygon.on("modifyPoly", updateLabel)
        polygon.on("modified", syncPoints)
      }

      if (isEditingVertices && !isPickingPoint) {
        polygon.on("mousedown", () => onZoneSelect?.(index))
      }

      canvas.add(polygon, label)
      if (isEditingVertices && isSelected && !isPickingPoint) {
        canvas.setActiveObject(polygon)
      }
    })

    const visibleServicePoints = zones.flatMap((zone, zoneIndex) => {
      const point = zoneIndex === selectedZoneIndex && servicePoint
        ? servicePoint
        : zone.service_point
      return point ? [{ point, zoneIndex }] : []
    })

    visibleServicePoints.forEach(({ point, zoneIndex }) => {
      const [x, y] = point
      const markerX = offsetX + x * scale
      const markerY = offsetY + y * scale
      const servicePointColor = getZoneColor(
        zones[zoneIndex],
        zoneIndex,
        zoneStates,
      ).stroke
      const servicePointLabel = new FabricText(zones[zoneIndex].name, {
        originX: "center",
        originY: "center",
        fill: "#ffffff",
        fontFamily: "Arial",
        fontSize: 11,
        fontWeight: "600",
        selectable: false,
        evented: false,
      })
      const labelWidth = (servicePointLabel.width ?? 64) + 16
      const labelHeight = (servicePointLabel.height ?? 13) + 8
      const badgeOffset = 26
      const pinCenterOffset = 12
      const canDragServicePoint =
        isEditingVertices
        && zoneIndex === selectedZoneIndex
        && !isPickingPoint
      const servicePointBadge = new Group(
        [
          new Rect({
            width: labelWidth,
            height: labelHeight,
            rx: labelHeight / 2,
            ry: labelHeight / 2,
            fill: servicePointColor,
            stroke: "#ffffff",
            strokeWidth: 1,
            originX: "center",
            originY: "center",
            selectable: false,
            evented: false,
          }),
          servicePointLabel,
        ],
        {
          left: markerX,
          top: markerY - badgeOffset,
          originX: "center",
          originY: "bottom",
          selectable: canDragServicePoint,
          evented: canDragServicePoint,
          hasControls: false,
          hasBorders: false,
          hoverCursor: "move",
          moveCursor: "move",
        },
      )
      const marker = new Path(
        "M20 10c0 5-5.5 10.2-7.4 11.8a1 1 0 0 1-1.2 0C9.5 20.2 4 15 4 10a8 8 0 1 1 16 0",
        {
          left: markerX,
          top: markerY,
          fill: servicePointColor,
          stroke: "#ffffff",
          strokeWidth: 1.75,
          strokeUniform: true,
          originX: "center",
          originY: "bottom",
          selectable: canDragServicePoint,
          evented: canDragServicePoint,
          hasControls: false,
          hasBorders: false,
          hoverCursor: "move",
          moveCursor: "move",
        },
      )
      const markerCenter = new Circle({
        left: markerX,
        top: markerY - pinCenterOffset,
        radius: 3,
        fill: "#ffffff",
        originX: "center",
        originY: "center",
        selectable: false,
        evented: false,
      })

      const syncServicePointVisuals = (pointX: number, pointY: number) => {
        const nextX = Math.min(
          Math.max(pointX, offsetX),
          offsetX + renderedW,
        )
        const nextY = Math.min(
          Math.max(pointY, offsetY),
          offsetY + renderedH,
        )
        marker.set({ left: nextX, top: nextY })
        markerCenter.set({ left: nextX, top: nextY - pinCenterOffset })
        servicePointBadge.set({ left: nextX, top: nextY - badgeOffset })
        marker.setCoords()
        markerCenter.setCoords()
        servicePointBadge.setCoords()
        canvas.requestRenderAll()
        return { x: nextX, y: nextY }
      }

      const commitServicePoint = (pointX: number, pointY: number) => {
        const nextPoint = syncServicePointVisuals(pointX, pointY)
        onServicePointChange?.([
          Math.round((nextPoint.x - offsetX) / scale),
          Math.round((nextPoint.y - offsetY) / scale),
        ])
      }

      if (canDragServicePoint) {
        marker.on("moving", () => {
          syncServicePointVisuals(marker.left ?? markerX, marker.top ?? markerY)
        })
        marker.on("modified", () => {
          commitServicePoint(marker.left ?? markerX, marker.top ?? markerY)
        })
        servicePointBadge.on("moving", () => {
          syncServicePointVisuals(
            servicePointBadge.left ?? markerX,
            (servicePointBadge.top ?? markerY - badgeOffset) + badgeOffset,
          )
        })
        servicePointBadge.on("modified", () => {
          commitServicePoint(
            servicePointBadge.left ?? markerX,
            (servicePointBadge.top ?? markerY - badgeOffset) + badgeOffset,
          )
        })
      }

      canvas.add(
        marker,
        markerCenter,
        servicePointBadge,
      )
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
  }, [
    previewSize,
    videoSize,
    zones,
    zoneStates,
    selectedZoneIndex,
    servicePoint,
    isEditingVertices,
    isAddingZone,
    isPickingServicePoint,
    draftPoints,
    onZoneSelect,
    onZonePointsChange,
    onServicePointChange,
  ])

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
      if (pts.length < 3) { isFinishingDraftRef.current = false; return }
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

  // ── Pick service point — mouse interaction ───────────────────────────────
  useEffect(() => {
    const canvas = fabricCanvasRef.current
    if (
      !canvas
      || !isPickingServicePoint
      || selectedZoneIndex === null
      || !previewSize.width
      || !videoSize.width
    ) return

    const scale = Math.min(
      previewSize.width / videoSize.width,
      previewSize.height / videoSize.height,
    )
    const renderedW = videoSize.width * scale
    const renderedH = videoSize.height * scale
    const offsetX = (previewSize.width - renderedW) / 2
    const offsetY = (previewSize.height - renderedH) / 2

    const handleMouseDown = (event: { e: MouseEvent | PointerEvent | TouchEvent }) => {
      const point = canvas.getScenePoint(event.e)
      const x = Math.round(
        (Math.min(Math.max(point.x, offsetX), offsetX + renderedW) - offsetX) / scale,
      )
      const y = Math.round(
        (Math.min(Math.max(point.y, offsetY), offsetY + renderedH) - offsetY) / scale,
      )
      onServicePointChange?.([x, y])
    }

    canvas.on("mouse:down", handleMouseDown)
    return () => { canvas.off("mouse:down", handleMouseDown) }
  }, [
    isPickingServicePoint,
    selectedZoneIndex,
    previewSize,
    videoSize,
    onServicePointChange,
  ])

  // ── Clear draft on mode exit ─────────────────────────────────────────────
  useEffect(() => {
    if (isAddingZone) return
    draftPointsRef.current = []
    isFinishingDraftRef.current = false
    lastDraftTapRef.current = null
    queueMicrotask(() => setDraftPoints([]))
  }, [isAddingZone])

  return (
    <div
      ref={overlayHostRef}
      className="pointer-events-none absolute inset-0 z-[2] h-full w-full"
    />
  )
}
