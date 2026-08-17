import { useEffect, useRef, useState } from "react"

import { Badge } from "@/components/ui/badge"
import type { CalibrationPointPosition } from "@/lib/calibration-points"
import { cn } from "@/lib/utils"
import {
  normalizedVideoPointToPixel,
  normalizedVideoPointToPreview,
  previewPointToNormalizedVideo,
} from "@/components/camera-preview/layout"
import { usePreviewSize } from "@/components/camera-preview/use-preview-size"

interface CalibrationPointsOverlayProps {
  points: CalibrationPointPosition[]
  videoSize: { width: number; height: number } | null
  selectedPointId: string | null
  onPointsChange: (points: CalibrationPointPosition[]) => void
  onPointSelect: (pointId: string | null) => void
  disabled?: boolean
}

function clamp(value: number) {
  return Math.min(Math.max(value, 0.03), 0.97)
}

const UNSELECTED_COLOR = "#FFF"  // sky blue
const SELECTED_COLOR   = "#78ec76"  // hot pink

export function CalibrationPointsOverlay({
  points,
  videoSize,
  selectedPointId,
  onPointsChange,
  onPointSelect,
  disabled = false,
}: CalibrationPointsOverlayProps) {
  const containerRef = useRef<HTMLDivElement>(null)
  const dragOffsetRef = useRef({ x: 0, y: 0 })
  const [draggingPointId, setDraggingPointId] = useState<string | null>(null)
  const previewSize = usePreviewSize(containerRef)

  useEffect(() => {
    if (!draggingPointId || disabled || !videoSize) return
    const activeVideoSize = videoSize

    function handlePointerMove(event: PointerEvent) {
      const rect = containerRef.current?.getBoundingClientRect()
      if (!rect?.width || !rect.height) return

      const normalized = previewPointToNormalizedVideo(
        {
          x: event.clientX - dragOffsetRef.current.x - rect.left,
          y: event.clientY - dragOffsetRef.current.y - rect.top,
        },
        previewSize,
        activeVideoSize,
      )
      if (!normalized) return
      const x = clamp(normalized.x)
      const y = clamp(normalized.y)
      onPointsChange(
        points.map((point) =>
          point.id === draggingPointId ? { ...point, x, y } : point,
        ),
      )
    }

    function handlePointerUp() {
      dragOffsetRef.current = { x: 0, y: 0 }
      setDraggingPointId(null)
    }

    window.addEventListener("pointermove", handlePointerMove)
    window.addEventListener("pointerup", handlePointerUp)
    return () => {
      window.removeEventListener("pointermove", handlePointerMove)
      window.removeEventListener("pointerup", handlePointerUp)
    }
  }, [disabled, draggingPointId, onPointsChange, points, previewSize, videoSize])

  return (
    <div
      ref={containerRef}
      className="absolute inset-0 z-30 touch-none select-none"
      onPointerDown={(event) => {
        if (!disabled && event.target === event.currentTarget) {
          onPointSelect(null)
        }
      }}
    >
      <style>{`
        @keyframes calibration-point-expand {
          0% {
            width: 8px;
            height: 8px;
            opacity: 0.8;
            border-width: 2px;
          }
          100% {
            width: 54px;
            height: 54px;
            opacity: 0;
            border-width: 0.5px;
          }
        }

        @media (prefers-reduced-motion: reduce) {
          .calibration-point-ring {
            animation: none !important;
          }
        }
      `}</style>

      {points.map((point) => {
        const selected = point.id === selectedPointId
        const dragging = point.id === draggingPointId
        const color = selected ? SELECTED_COLOR : UNSELECTED_COLOR
        const previewPoint = videoSize
          ? normalizedVideoPointToPreview(point, previewSize, videoSize)
          : null
        const pixelPoint = videoSize
          ? normalizedVideoPointToPixel(point, videoSize)
          : null

        if (!previewPoint) return null

        return (
          <button
            key={point.id}
            type="button"
            aria-label={`Di chuyển ${point.label}`}
            onPointerDown={(event) => {
              if (disabled) return
              event.preventDefault()
              const rect = containerRef.current?.getBoundingClientRect()
              if (rect) {
                dragOffsetRef.current = {
                  x: event.clientX - (rect.left + previewPoint.x),
                  y: event.clientY - (rect.top + previewPoint.y),
                }
              }
              onPointSelect(point.id)
              setDraggingPointId(point.id)
            }}
            className={cn(
              "pointer-events-auto absolute grid size-11 -translate-x-1/2 -translate-y-1/2 cursor-grab place-items-center rounded-full transition-opacity duration-200 active:cursor-grabbing",
              disabled && "pointer-events-none opacity-60",
            )}
            style={{
              left: previewPoint.x,
              top: previewPoint.y,
            }}
          >
            <span
              className={cn(
                "absolute z-10 size-2 rounded-full transition-all duration-200",
                dragging && "scale-125",
              )}
              style={{
                backgroundColor: color,
                boxShadow: `0 0 0 2px rgba(0, 0, 0, 0.75), 0 0 ${selected ? 10 : 8}px ${color}`,
              }}
            />

            <span
              className={cn(
                "calibration-point-ring absolute rounded-full border-2",
                selected ? "size-[26px] opacity-90" : "size-2",
              )}
              style={
                selected
                  ? { borderColor: color }
                  : {
                      borderColor: color,
                      animation:
                        "calibration-point-expand 2s cubic-bezier(.25,.6,.4,1) infinite",
                    }
              }
            />

            <span
              className={cn(
                "calibration-point-ring absolute rounded-full border-2",
                selected ? "size-[38px] opacity-40" : "size-2",
              )}
              style={
                selected
                  ? { borderColor: color }
                  : {
                      borderColor: color,
                      animation:
                        "calibration-point-expand 2s cubic-bezier(.25,.6,.4,1) 1s infinite",
                    }
              }
            />

            <Badge
              variant={selected ? "default" : "secondary"}
              className={cn(
                "pointer-events-auto absolute -top-4 left-1/2 z-20 -translate-x-1/2 cursor-grab px-1.5 text-[10px] shadow-sm active:cursor-grabbing",
                selected && "border-transparent text-slate-950",
              )}
              style={selected ? { backgroundColor: SELECTED_COLOR } : undefined}
            >
              {pixelPoint
                ? `${point.label} (${Math.round(pixelPoint.x)} · ${Math.round(pixelPoint.y)})`
                : point.label}
            </Badge>
          </button>
        )
      })}
    </div>
  )
}
