import { memo, useEffect, useState } from "react"
import { Play, RotateCcw, Square } from "lucide-react"
import { Link } from "react-router-dom"
import { toast } from "sonner"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select"
import { Skeleton } from "@/components/ui/skeleton"
import { Spinner } from "@/components/ui/spinner"
import { CameraPreview } from "@/components/camera-preview"
import { runtimeApi, type RuntimeStatus } from "@/api/runtime.api"
import { useAutoStartConfig, useUpdateAutoStartConfig } from "@/hooks/use-auto-start"
import { useCameras, type Camera } from "@/hooks/use-cameras"
import { useRuntimeStatus } from "@/hooks/use-runtime-status"
import { cn } from "@/lib/utils"

// ── Runtime card ─────────────────────────────────────────────────────────────

type RuntimeDisplayState = "running" | "stopped" | "starting" | "stopping" | "restarting" | "error"

const STATUS_CONFIG: Record<RuntimeDisplayState, { label: string; dotClass: string; badgeClass: string }> = {
  running:    { label: "Running",       dotClass: "bg-green-500",  badgeClass: "border-green-500/30 bg-green-500/10 text-green-600 dark:text-green-400" },
  stopped:    { label: "Stopped",       dotClass: "bg-zinc-400",   badgeClass: "border-border bg-muted text-muted-foreground" },
  starting:   { label: "Starting...",   dotClass: "bg-amber-400",  badgeClass: "border-amber-500/30 bg-amber-500/10 text-amber-600 dark:text-amber-400" },
  stopping:   { label: "Stopping...",   dotClass: "bg-amber-400",  badgeClass: "border-amber-500/30 bg-amber-500/10 text-amber-600 dark:text-amber-400" },
  restarting: { label: "Restarting...", dotClass: "bg-blue-400",   badgeClass: "border-blue-500/30 bg-blue-500/10 text-blue-600 dark:text-blue-400" },
  error:      { label: "Error",         dotClass: "bg-red-500",    badgeClass: "border-red-500/30 bg-red-500/10 text-red-600 dark:text-red-400" },
}

function formatUptime(seconds: number): string {
  const d = Math.floor(seconds / 86400)
  const h = Math.floor(seconds / 3600)
  const hInDay = Math.floor((seconds % 86400) / 3600)
  const m = Math.floor((seconds % 3600) / 60)
  const s = Math.floor(seconds % 60)
  if (d > 0) return `${d} ngày ${hInDay} giờ ${m} phút`
  if (h > 0) return `${h} giờ ${m} phút`
  if (m > 0) return `${m} phút ${s} giây`
  return `${s} giây`
}

function getStatusSub(displayState: RuntimeDisplayState, rtStatus: RuntimeStatus | null): string {
  switch (displayState) {
    case "running":
      return rtStatus?.uptime_seconds != null
        ? `Đã chạy ${formatUptime(rtStatus.uptime_seconds)}`
        : "Đang chạy..."
    case "stopped":
      return rtStatus?.stopped_at
        ? `Dừng lúc ${new Date(rtStatus.stopped_at).toLocaleTimeString("vi-VN", { hour: "2-digit", minute: "2-digit" })}`
        : "Đã dừng"
    case "error":
      return rtStatus?.last_error ?? "Lỗi không xác định"
    case "starting":   return "Đang khởi động..."
    case "stopping":   return "Đang dừng..."
    case "restarting": return "Đang khởi động lại..."
  }
}

function RuntimeCard() {
  const { status: rtStatus, connected } = useRuntimeStatus()
  const { data: autoStartConfig } = useAutoStartConfig()
  const updateAutoStart = useUpdateAutoStartConfig()
  const [isRestarting, setIsRestarting] = useState(false)
  const [isActing, setIsActing] = useState(false)

  const wsState = rtStatus?.state ?? null
  const autoStart = autoStartConfig?.auto_start ?? false

  useEffect(() => {
    if (isRestarting && (wsState === "running" || wsState === "error")) {
      setIsRestarting(false)
    }
  }, [wsState, isRestarting])

  const displayState: RuntimeDisplayState = (() => {
    if (wsState === null) return "stopped"
    if (isRestarting && wsState !== "running" && wsState !== "error") return "restarting"
    return wsState
  })()

  const transitioning = displayState === "starting" || displayState === "stopping" || displayState === "restarting"
  const s = STATUS_CONFIG[displayState]
  const sub = rtStatus === null && !connected
    ? "Đang kết nối tới server..."
    : getStatusSub(displayState, rtStatus)

  const buttonsDisabled = !connected || transitioning || isActing

  async function handleStart() {
    setIsActing(true)
    try {
      await runtimeApi.start()
    } catch (e) {
      toast.error(e instanceof Error ? e.message : "Không thể khởi động runtime")
    } finally {
      setIsActing(false)
    }
  }

  async function handleStop() {
    setIsActing(true)
    try {
      await runtimeApi.stop()
    } catch (e) {
      toast.error(e instanceof Error ? e.message : "Không thể dừng runtime")
    } finally {
      setIsActing(false)
    }
  }

  async function handleRestart() {
    setIsRestarting(true)
    setIsActing(true)
    try {
      await runtimeApi.restart()
    } catch (e) {
      toast.error(e instanceof Error ? e.message : "Không thể khởi động lại runtime")
      setIsRestarting(false)
    } finally {
      setIsActing(false)
    }
  }

  return (
    <Card>
      <CardContent className="flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between">

        {/* Status */}
        <div className="flex items-center gap-3">
          <div className="relative flex size-4 shrink-0 items-center justify-center">
            {transitioning ? (
              <Spinner className="text-muted-foreground" />
            ) : (
              <span className="relative flex size-3">
                <span className={cn("absolute inline-flex size-full animate-ping rounded-full opacity-60", s.dotClass)} />
                <span className={cn("relative inline-flex size-3 rounded-full", s.dotClass)} />
              </span>
            )}
          </div>
          <div className="flex flex-col gap-1">
            <div className="flex items-center gap-2">
              <span className="text-sm font-semibold">AI Detection Runtime</span>
              <Badge variant="outline" className={cn("text-[11px]", s.badgeClass)}>
                {s.label}
              </Badge>
            </div>
            <span className="text-xs text-muted-foreground">{sub}</span>
          </div>
        </div>

        {/* Controls */}
        <div className="flex flex-wrap items-center gap-2">
          <div className="flex items-center gap-2">
            <span className="text-xs font-medium text-muted-foreground">Auto start</span>
            <Select
              value={autoStart ? "true" : "false"}
              disabled={updateAutoStart.isPending}
              onValueChange={(value) => {
                updateAutoStart.mutate(
                  { auto_start: value === "true" },
                  {
                    onError: (e) => {
                      toast.error(e instanceof Error ? e.message : "Không thể cập nhật auto start")
                    },
                  },
                )
              }}
            >
              <SelectTrigger size="sm" className="w-[100px]">
                <SelectValue />
              </SelectTrigger>
              <SelectContent position="popper" className="w-fit min-w-0">
                <SelectItem value="true">Enabled</SelectItem>
                <SelectItem value="false">Disabled</SelectItem>
              </SelectContent>
            </Select>
          </div>
          <Button
            size="sm"
            className="flex-1 sm:flex-none"
            disabled={buttonsDisabled || displayState === "running"}
            onClick={handleStart}
          >
            <Play />
            Start
          </Button>
          <Button
            size="sm"
            variant="destructive"
            className="flex-1 sm:flex-none"
            disabled={buttonsDisabled || displayState === "stopped"}
            onClick={handleStop}
          >
            <Square />
            Stop
          </Button>
          <Button
            size="sm"
            variant="outline"
            className="flex-1 sm:flex-none"
            disabled={buttonsDisabled || displayState === "stopped"}
            onClick={handleRestart}
          >
            <RotateCcw />
            Restart
          </Button>
        </div>

      </CardContent>
    </Card>
  )
}

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

      {/* Runtime control */}
      <RuntimeCard />

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
