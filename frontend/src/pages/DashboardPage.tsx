import { memo } from "react"
import { Link } from "react-router-dom"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { Skeleton } from "@/components/ui/skeleton"
import { CameraPreview } from "@/components/camera-preview"
import { useCameras, type Camera } from "@/hooks/use-cameras"
import { cn } from "@/lib/utils"

// ── Camera cell ───────────────────────────────────────────────────────────────

const CameraCell = memo(function CameraCell({ camera }: { camera: Camera }) {
  return (
    <Link
      to={`/cameras/${camera.id}`}
      className="relative block aspect-video overflow-hidden rounded-lg ring-1 ring-border transition-shadow hover:ring-2 hover:ring-ring"
    >
      <CameraPreview
        src={camera.webrtc_address ?? ""}
        zones={camera.zones}
        bboxCameraId={camera.id}
        hideFaceKeypoints={true}
      />
      <div className="pointer-events-none absolute bottom-3 left-3 z-30 rounded-md bg-black/60 px-2.5 py-1 text-xs font-medium text-white backdrop-blur-sm">
        {camera.name}
      </div>
    </Link>
  )
})

// ── Page ──────────────────────────────────────────────────────────────────────

export function DashboardPage() {
  const { data: cameras = [], isLoading: camerasLoading } = useCameras()
  const gridCols = cameras.length <= 1 ? "grid-cols-1" : "grid-cols-1 sm:grid-cols-2"

  return (
    <div className="flex flex-col gap-6">

      {/* Camera grid */}
      <Card>
        <CardHeader>
          <CardTitle>Cameras</CardTitle>
        </CardHeader>
        <CardContent>
          {camerasLoading ? (
            <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
              <Skeleton className="aspect-video rounded-lg" />
              <Skeleton className="aspect-video rounded-lg" />
            </div>
          ) : cameras.length === 0 ? (
            <p className="py-8 text-center text-sm text-muted-foreground">Chưa có camera nào.</p>
          ) : (
            <div className={cn("grid gap-4", gridCols)}>
              {cameras.map((cam) => (
                <CameraCell key={cam.id} camera={cam} />
              ))}
            </div>
          )}
        </CardContent>
      </Card>

    </div>
  )
}
