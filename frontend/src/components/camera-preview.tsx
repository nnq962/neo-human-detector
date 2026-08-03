import { lazy, Suspense, useRef, useState } from "react"
import type { Zone } from "@/api/cameras.api"
import type { RuntimeZonePayload } from "@/lib/bbox-stream"
import { cn } from "@/lib/utils"
import { DetectionOverlay } from "./camera-preview/detection-overlay"
import { computeLayout } from "./camera-preview/layout"
import { RobotOverlay } from "./camera-preview/robot-overlay"
import { StreamStatusOverlay } from "./camera-preview/stream-status-overlay"
import type { VideoSize } from "./camera-preview/types"
import { usePreviewSize } from "./camera-preview/use-preview-size"
import { useWhepStream } from "./camera-preview/use-whep-stream"

const ZoneOverlay = lazy(() =>
  import("./camera-preview/zone-overlay").then((module) => ({
    default: module.ZoneOverlay,
  })),
)

export interface CameraPreviewProps {
  src: string
  cameraId?: string | null
  className?: string
  reconnectKey?: number
  zones?: Zone[]
  isAddingZone?: boolean
  isEditingVertices?: boolean
  isPickingServicePoint?: boolean
  selectedZoneIndex?: number | null
  servicePoint?: [number, number] | null
  onZoneAdd?: (points: number[][]) => void
  onZonePointsChange?: (index: number, points: number[][]) => void
  onZoneSelect?: (index: number) => void
  onServicePointChange?: (point: [number, number]) => void
  /** Bật overlay detection realtime cho camera này (subscribe WS dùng chung). */
  bboxCameraId?: string | null
  hideFaceKeypoints?: boolean
  hideStreamBadges?: boolean
  videoBorderRadius?: number
  onVideoSizeChange?: (size: VideoSize | null) => void
}

const EMPTY_ZONES: Zone[] = []

export function CameraPreview({
  src,
  cameraId = null,
  className,
  reconnectKey = 0,
  zones = EMPTY_ZONES,
  isAddingZone = false,
  isEditingVertices = false,
  isPickingServicePoint = false,
  selectedZoneIndex = null,
  servicePoint = null,
  onZoneAdd,
  onZonePointsChange,
  onZoneSelect,
  onServicePointChange,
  bboxCameraId = null,
  hideFaceKeypoints = false,
  hideStreamBadges = false,
  videoBorderRadius = 0,
  onVideoSizeChange,
}: CameraPreviewProps) {
  const containerRef = useRef<HTMLDivElement>(null)
  const videoRef = useRef<HTMLVideoElement>(null)
  const [zoneStates, setZoneStates] = useState<
    Record<string, RuntimeZonePayload> | undefined
  >(undefined)

  const previewSize = usePreviewSize(containerRef)
  const { status, errorMessage, resolution, videoSize } = useWhepStream({
    src,
    reconnectKey,
    videoRef,
    onVideoSizeChange,
  })

  const videoLayout = computeLayout(previewSize, videoSize)
  const hasZoneEditingCapabilities = Boolean(
    onZoneAdd
    || onZonePointsChange
    || onZoneSelect
    || onServicePointChange,
  )
  const shouldRenderZoneOverlay = zones.length > 0
    || hasZoneEditingCapabilities
    || isAddingZone
    || isEditingVertices
    || isPickingServicePoint
  const videoClipPath = videoBorderRadius > 0
    ? videoLayout
      ? `inset(${videoLayout.offsetY}px ${videoLayout.offsetX}px ${videoLayout.offsetY}px ${videoLayout.offsetX}px round ${videoBorderRadius}px)`
      : `inset(0 round ${videoBorderRadius}px)`
    : undefined

  return (
    <div
      ref={containerRef}
      className={cn(
        "relative h-full w-full overflow-hidden bg-black",
        className,
      )}
    >
      <video
        ref={videoRef}
        autoPlay
        muted
        playsInline
        className="absolute inset-0 h-full w-full object-contain"
        style={{ clipPath: videoClipPath }}
      />

      {shouldRenderZoneOverlay && (
        <Suspense fallback={null}>
          <ZoneOverlay
            zones={zones}
            zoneStates={zoneStates}
            previewSize={previewSize}
            videoSize={videoSize}
            isAddingZone={isAddingZone}
            isEditingVertices={isEditingVertices}
            isPickingServicePoint={isPickingServicePoint}
            selectedZoneIndex={selectedZoneIndex}
            servicePoint={servicePoint}
            onZoneAdd={onZoneAdd}
            onZonePointsChange={onZonePointsChange}
            onZoneSelect={onZoneSelect}
            onServicePointChange={onServicePointChange}
          />
        </Suspense>
      )}

      <DetectionOverlay
        cameraId={bboxCameraId}
        previewSize={previewSize}
        videoSize={videoSize}
        hideFaceKeypoints={hideFaceKeypoints}
        onZoneStatesChange={setZoneStates}
      />

      <RobotOverlay
        cameraId={cameraId}
        previewSize={previewSize}
        videoSize={videoSize}
      />

      <StreamStatusOverlay
        status={status}
        errorMessage={errorMessage}
        resolution={resolution}
        hideBadges={hideStreamBadges}
      />
    </div>
  )
}
