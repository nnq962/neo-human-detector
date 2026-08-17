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
import { Button } from "@/components/ui/button"
import { useCamera } from "@/hooks/use-camera"
import { useCameraCalibration } from "@/hooks/use-camera-calibration"

export function CameraCalibrationPage() {
  const { id = "" } = useParams<{ id: string }>()
  return <CameraCalibrationWorkspace key={id} cameraId={id} />
}

function CameraCalibrationWorkspace({ cameraId }: { cameraId: string }) {
  const { data: camera, isLoading, isError } = useCamera(cameraId)
  const calibration = useCameraCalibration(cameraId, Boolean(camera))
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
      <div className="flex flex-col gap-4">
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
    <div className="flex flex-col gap-4">
      <CalibrationSummaryCard camera={camera} calibration={calibration} />

      {calibration.calibrationLoadError && (
        <Card className="border-destructive/40 bg-destructive/5">
          <CardContent className="flex items-center justify-between gap-4 py-3 text-sm">
            <span>{calibration.calibrationLoadError}</span>
            <Button
              type="button"
              variant="outline"
              size="sm"
              onClick={calibration.reloadCalibration}
            >
              Thử lại
            </Button>
          </CardContent>
        </Card>
      )}

      <Card className="gap-0 py-0">
        <CardHeader className="py-4">
          <CardTitle>Hiệu chỉnh tọa độ</CardTitle>
          <CardDescription>
            Chọn điểm ảnh tương ứng với vị trí robot trong hệ tọa độ thực.
          </CardDescription>
        </CardHeader>

        <CardContent className="p-0 pb-4">
          <div className="flex w-full flex-col overflow-hidden lg:grid lg:grid-cols-[minmax(0,56rem)_minmax(20rem,1fr)]">
            <div
              ref={videoPanelRef}
              className="relative aspect-video w-full min-w-0 self-start overflow-hidden bg-black"
            >
              <CameraPreview
                src={camera.webrtc_address ?? ""}
                cameraId={camera.id}
                onVideoSizeChange={calibration.setVideoSize}
              />
              <CalibrationPointsOverlay
                points={calibration.points}
                videoSize={calibration.videoSize}
                selectedPointId={calibration.selectedPointId}
                onPointsChange={calibration.updatePointPositions}
                onPointSelect={calibration.setSelectedPointId}
                disabled={
                  calibration.isLoadingCalibration
                  || Boolean(calibration.calibrationLoadError)
                  || calibration.isApplyingCalibration
                  || calibration.isDeletingCalibration
                }
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
