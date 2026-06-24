import { useEffect, useRef, useState } from "react"
import { Canvas, Circle, FabricText, Point, Polygon, Polyline, controlsUtils } from "fabric"
import { cn } from "@/lib/utils"
import type { Zone } from "@/api/cameras.api"

// ── Types ────────────────────────────────────────────────────────────────────

type StreamStatus = "connecting" | "live" | "error"
type PreviewSize = { width: number; height: number }
type VideoSize = { width: number; height: number }
type OfferData = { iceUfrag: string; icePwd: string; medias: string[] }

// ── WHEP helpers ─────────────────────────────────────────────────────────────

const DOUBLE_TAP_MAX_DELAY_MS = 350
const DOUBLE_TAP_MAX_DISTANCE_PX = 28

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

// ── Fabric helpers ────────────────────────────────────────────────────────────

const zoneColors = [
  { fill: "rgba(14, 165, 233, 0.22)", stroke: "#0ea5e9" },
  { fill: "rgba(16, 185, 129, 0.22)", stroke: "#10b981" },
  { fill: "rgba(245, 158, 11, 0.24)", stroke: "#f59e0b" },
  { fill: "rgba(244, 63, 94, 0.22)",  stroke: "#f43f5e" },
  { fill: "rgba(139, 92, 246, 0.22)", stroke: "#8b5cf6" },
  { fill: "rgba(236, 72, 153, 0.22)", stroke: "#ec4899" },
]

function getAbsolutePolygonPoints(polygon: Polygon) {
  const transform = polygon.calcTransformMatrix()
  return polygon.points.map((p) =>
    new Point(p.x - polygon.pathOffset.x, p.y - polygon.pathOffset.y).transform(transform),
  )
}

function getContainedVideoRect(preview: PreviewSize, source: VideoSize) {
  if (!preview.width || !preview.height || !source.width || !source.height) return null
  const scale = Math.min(preview.width / source.width, preview.height / source.height)
  const width = source.width * scale
  const height = source.height * scale
  return {
    scale,
    width,
    height,
    offsetX: (preview.width - width) / 2,
    offsetY: (preview.height - height) / 2,
  }
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
}

// ── Component ─────────────────────────────────────────────────────────────────

export function CameraPreview({
  src,
  reconnectKey = 0,
  zones = [],
  isAddingZone = false,
  isEditingVertices = false,
  selectedZoneIndex = null,
  onZoneAdd,
  onZonePointsChange,
  onZoneSelect,
}: CameraPreviewProps) {
  const containerRef    = useRef<HTMLDivElement>(null)
  const videoRef        = useRef<HTMLVideoElement>(null)
  const overlayCanvasRef = useRef<HTMLCanvasElement>(null)
  const fabricCanvasRef  = useRef<Canvas | null>(null)
  const isFinishingDraftRef = useRef(false)
  const draftPointsRef      = useRef<number[][]>([])
  const lastDraftTapRef     = useRef<{ time: number; x: number; y: number } | null>(null)

  const [status, setStatus]         = useState<StreamStatus>("connecting")
  const [errorMessage, setError]    = useState("")
  const [resolution, setResolution] = useState("Detecting...")
  const [previewSize, setPreviewSize] = useState<PreviewSize>({ width: 0, height: 0 })
  const [videoSize, setVideoSize]     = useState<VideoSize>({ width: 0, height: 0 })
  const [draftPoints, setDraftPoints] = useState<number[][]>([])

  // ── Fabric canvas init ───────────────────────────────────────────────────
  useEffect(() => {
    const el = overlayCanvasRef.current
    if (!el) return

    const canvas = new Canvas(el, { selection: false, renderOnAddRemove: false })
    canvas.defaultCursor = "default"
    canvas.hoverCursor   = "default"
    Object.assign(canvas.wrapperEl.style, {
      position: "absolute", inset: "0", width: "100%", height: "100%", zIndex: "1",
      pointerEvents: "none",
    })
    canvas.upperCanvasEl.style.pointerEvents = "none"
    canvas.upperCanvasEl.style.touchAction   = "none"
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
    canvas.wrapperEl.style.pointerEvents     = isInteractive ? "auto" : "none"
    canvas.upperCanvasEl.style.pointerEvents = isInteractive ? "auto" : "none"
    canvas.defaultCursor = isAddingZone ? "crosshair" : "default"
    canvas.hoverCursor   = isAddingZone ? "crosshair" : isEditingVertices ? "move" : "default"
    canvas.clear()

    if (!videoSize.width || !videoSize.height) { canvas.requestRenderAll(); return }

    const scale = Math.min(previewSize.width / videoSize.width, previewSize.height / videoSize.height)
    const renderedW = videoSize.width * scale
    const renderedH = videoSize.height * scale
    const offsetX = (previewSize.width  - renderedW) / 2
    const offsetY = (previewSize.height - renderedH) / 2

    zones.forEach((zone, index) => {
      const color     = zoneColors[index % zoneColors.length]
      const isSelected = index === selectedZoneIndex
      const points    = zone.points.map(([x, y]) => ({ x: offsetX + x * scale, y: offsetY + y * scale }))
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
  }, [previewSize, videoSize, zones, selectedZoneIndex, isEditingVertices, isAddingZone, draftPoints, onZoneSelect, onZonePointsChange])

  // ── Add zone — mouse interaction ─────────────────────────────────────────
  useEffect(() => {
    const canvas = fabricCanvasRef.current
    if (!canvas || !isAddingZone || !previewSize.width || !videoSize.width) return

    const scale = Math.min(previewSize.width / videoSize.width, previewSize.height / videoSize.height)
    const renderedW = videoSize.width * scale
    const renderedH = videoSize.height * scale
    const offsetX = (previewSize.width  - renderedW) / 2
    const offsetY = (previewSize.height - renderedH) / 2

    const toImagePoint = (p: Point) => [
      Math.round((Math.min(Math.max(p.x, offsetX), offsetX + renderedW) - offsetX) / scale),
      Math.round((Math.min(Math.max(p.y, offsetY), offsetY + renderedH) - offsetY) / scale),
    ]

    const isDoubleTap = (e: MouseEvent | PointerEvent | TouchEvent, p: Point) => {
      const now = e.timeStamp || Date.now()
      const last = lastDraftTapRef.current
      if (!last) { lastDraftTapRef.current = { time: now, x: p.x, y: p.y }; return false }
      const elapsed  = now - last.time
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

    let closed = false
    let sessionUrl = ""
    let offerData: OfferData | null = null
    const queued: RTCIceCandidate[] = []
    const pc = new RTCPeerConnection()

    const updateResolution = () => {
      const { videoWidth: w, videoHeight: h } = video
      setResolution(w > 0 && h > 0 ? `${w} × ${h}` : "Detecting...")
      setVideoSize({ width: w, height: h })
    }

    const closeStream = () => {
      closed = true
      if (sessionUrl) fetch(sessionUrl, { method: "DELETE" }).catch(() => undefined)
      pc.getSenders().forEach((s) => s.track?.stop())
      pc.getReceivers().forEach((r) => r.track?.stop())
      pc.close(); video.pause(); video.srcObject = null
    }

    const sendCandidates = (cs: RTCIceCandidate[]) => {
      if (!offerData || !sessionUrl || !cs.length) return
      fetch(sessionUrl, {
        method: "PATCH",
        headers: { "Content-Type": "application/trickle-ice-sdpfrag", "If-Match": "*" },
        body: generateSdpFragment(offerData, cs),
      }).catch(() => undefined)
    }

    const connect = async () => {
      setStatus("connecting"); setError(""); setResolution("Detecting...")
      try {
        const optRes = await fetch(endpointUrl, { method: "OPTIONS" })
        const iceServers = parseIceServers(optRes.headers.get("link"))
        if (iceServers.length) pc.setConfiguration({ iceServers })

        pc.addTransceiver("video", { direction: "recvonly" })
        pc.addTransceiver("audio", { direction: "recvonly" })
        pc.createDataChannel("")

        pc.ontrack = (e) => { if (!closed || !video.srcObject) video.srcObject = e.streams[0] }
        pc.onconnectionstatechange = () => {
          if (closed) return
          if (pc.connectionState === "connected") setStatus("live")
          if (["failed", "disconnected", "closed"].includes(pc.connectionState)) {
            setStatus("error"); setError(`WebRTC ${pc.connectionState}`)
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
        if (!closed) await video.play()
      } catch (err) {
        if (closed) return
        setStatus("error"); setResolution("Unavailable")
        setError(err instanceof Error ? err.message : "Không thể mở stream")
      }
    }

    video.addEventListener("loadedmetadata", updateResolution)
    video.addEventListener("resize", updateResolution)
    connect()
    return () => {
      video.removeEventListener("loadedmetadata", updateResolution)
      video.removeEventListener("resize", updateResolution)
      closeStream()
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
            "bg-red-400":   status === "error",
          })} />
        </span>
        {status === "live" ? "Live" : status === "connecting" ? "Connecting" : "Error"}
      </div>
    </div>
  )
}
