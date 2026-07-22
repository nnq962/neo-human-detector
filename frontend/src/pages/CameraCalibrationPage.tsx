import { useEffect, useRef, useState } from "react"
import { useParams } from "react-router-dom"

import { CalibrationPointEditor } from "@/components/camera-calibration/calibration-point-editor"
import { CalibrationSummaryCard } from "@/components/camera-calibration/calibration-summary-card"
import { CalibrationPointsOverlay } from "@/components/calibration-points-overlay"
import { CameraPreview } from "@/components/camera-preview"
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card"
import { Skeleton } from "@/components/ui/skeleton"
import { useCamera } from "@/hooks/use-camera"
import { useCameraCalibration } from "@/hooks/use-camera-calibration"

export function CameraCalibrationPage() {
  const { id = "" } = useParams<{ id: string }>()
  const { data: camera, isLoading, isError } = useCamera(id)
  const calibration = useCameraCalibration(id, Boolean(camera))
  const videoPanelRef = useRef<HTMLDivElement>(null)
  const [videoPanelHeight, setVideoPanelHeight] = useState<number | null>(null)

  useEffect(() => {
    const element = videoPanelRef.current
    if (!element || !camera) return

    const updateHeight = () => setVideoPanelHeight(element.offsetHeight)
    updateHeight()

    const observer = new ResizeObserver(updateHeight)
    observer.observe(element)
    return () => observer.disconnect()
  }, [camera])

  if (isLoading) {
    return (
      <div className="flex flex-col gap-6">
        <Skeleton className="h-20 rounded-xl" />
        <Skeleton className="h-[560px] rounded-xl" />
      </div>
    )
  }

  if (isError || !camera) {
    return (
      <Card>
        <CardContent className="py-12 text-center text-sm text-muted-foreground">
          Không tìm thấy camera.
        </CardContent>
      </Card>
    )
  }

  return (
    <div className="flex flex-col gap-6">
      <CalibrationSummaryCard camera={camera} calibration={calibration} />

      <Card className="gap-0 py-0">
        <CardHeader className="py-4">
          <CardTitle>Hiệu chỉnh tọa độ</CardTitle>
          <CardDescription>
            Chọn điểm ảnh tương ứng với vị trí robot trong hệ tọa độ thực.
          </CardDescription>
        </CardHeader>

        <CardContent className="p-0 pb-4">
          <div className="flex flex-col overflow-hidden lg:grid lg:grid-cols-[minmax(0,1fr)_20rem]">
            <div
              ref={videoPanelRef}
              className="relative aspect-video w-full min-w-0 self-start overflow-hidden bg-black"
            >
              <CameraPreview
                src={camera.webrtc_address ?? ""}
                onVideoSizeChange={calibration.setVideoSize}
              />
              <CalibrationPointsOverlay
                points={calibration.points}
                videoSize={calibration.videoSize}
                selectedPointId={calibration.selectedPointId}
                onPointsChange={calibration.updatePointPositions}
                onPointSelect={calibration.setSelectedPointId}
              />
            </div>

            <CalibrationPointEditor
              calibration={calibration}
              panelHeight={videoPanelHeight}
            />
          </div>
        </CardContent>
      </Card>
    </div>
  )
}
