import { useEffect, useState } from "react"
import { LogIn, LogOut, Play, RotateCcw, Square } from "lucide-react"
import { Link } from "react-router-dom"
import { toast } from "sonner"
import {
  Area,
  AreaChart,
  CartesianGrid,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { ScrollArea } from "@/components/ui/scroll-area"
import { Skeleton } from "@/components/ui/skeleton"
import { Spinner } from "@/components/ui/spinner"
import { CameraPreview } from "@/components/camera-preview"
import { runtimeApi, type RuntimeStatus } from "@/api/runtime.api"
import { useCameras, type Camera } from "@/hooks/use-cameras"
import { useRuntimeStatus } from "@/hooks/use-runtime-status"
import { cn } from "@/lib/utils"

// ── Mock data ─────────────────────────────────────────────────────────────────


const mockEvents = [
  { id: 1,  ts: "14:32:11", camera: "AI Center",      zone: "hi 2", type: "enter" as const, pid: "P-042" },
  { id: 2,  ts: "14:28:44", camera: "AI Center",      zone: "hi 2", type: "exit"  as const, pid: "P-039" },
  { id: 3,  ts: "14:21:03", camera: "Android Center", zone: "hi 2", type: "enter" as const, pid: "P-017" },
  { id: 4,  ts: "14:18:59", camera: "Android Center", zone: "hi 2", type: "exit"  as const, pid: "P-017" },
  { id: 5,  ts: "14:11:22", camera: "AI Center",      zone: "hi 2", type: "enter" as const, pid: "P-031" },
  { id: 6,  ts: "13:58:07", camera: "AI Center",      zone: "hi 2", type: "exit"  as const, pid: "P-031" },
  { id: 7,  ts: "13:47:30", camera: "Android Center", zone: "hi 2", type: "enter" as const, pid: "P-008" },
  { id: 8,  ts: "13:41:15", camera: "AI Center",      zone: "hi 2", type: "enter" as const, pid: "P-042" },
  { id: 9,  ts: "13:33:52", camera: "Android Center", zone: "hi 2", type: "exit"  as const, pid: "P-008" },
  { id: 10, ts: "13:20:01", camera: "AI Center",      zone: "hi 2", type: "enter" as const, pid: "P-055" },
]

const mockHourlyData = [
  { hour: "00:00", count: 0  },
  { hour: "02:00", count: 0  },
  { hour: "04:00", count: 1  },
  { hour: "06:00", count: 3  },
  { hour: "08:00", count: 12 },
  { hour: "10:00", count: 18 },
  { hour: "12:00", count: 15 },
  { hour: "14:00", count: 20 },
  { hour: "16:00", count: 14 },
  { hour: "18:00", count: 8  },
  { hour: "20:00", count: 4  },
  { hour: "22:00", count: 1  },
]

// ── Pipeline card ─────────────────────────────────────────────────────────────

type PipelineStatus = "running" | "stopped" | "starting" | "stopping" | "restarting" | "error"

const STATUS_CONFIG: Record<PipelineStatus, { label: string; dotClass: string; badgeClass: string }> = {
  running:    { label: "Running",       dotClass: "bg-green-500",  badgeClass: "border-green-500/30 bg-green-500/10 text-green-600 dark:text-green-400" },
  stopped:    { label: "Stopped",       dotClass: "bg-zinc-400",   badgeClass: "border-border bg-muted text-muted-foreground" },
  starting:   { label: "Starting...",   dotClass: "bg-amber-400",  badgeClass: "border-amber-500/30 bg-amber-500/10 text-amber-600 dark:text-amber-400" },
  stopping:   { label: "Stopping...",   dotClass: "bg-amber-400",  badgeClass: "border-amber-500/30 bg-amber-500/10 text-amber-600 dark:text-amber-400" },
  restarting: { label: "Restarting...", dotClass: "bg-blue-400",   badgeClass: "border-blue-500/30 bg-blue-500/10 text-blue-600 dark:text-blue-400" },
  error:      { label: "Error",         dotClass: "bg-red-500",    badgeClass: "border-red-500/30 bg-red-500/10 text-red-600 dark:text-red-400" },
}

function formatUptime(seconds: number): string {
  const h = Math.floor(seconds / 3600)
  const m = Math.floor((seconds % 3600) / 60)
  const s = Math.floor(seconds % 60)
  if (h > 0) return `${h} giờ ${m} phút`
  if (m > 0) return `${m} phút ${s} giây`
  return `${s} giây`
}

function getStatusSub(displayState: PipelineStatus, rtStatus: RuntimeStatus | null): string {
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

function PipelineCard() {
  const { status: rtStatus, connected } = useRuntimeStatus()
  const [isRestarting, setIsRestarting] = useState(false)
  const [isActing, setIsActing] = useState(false)

  const wsState = rtStatus?.state ?? null

  useEffect(() => {
    if (isRestarting && (wsState === "running" || wsState === "error")) {
      setIsRestarting(false)
    }
  }, [wsState, isRestarting])

  const displayState: PipelineStatus = (() => {
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
      toast.error(e instanceof Error ? e.message : "Không thể khởi động pipeline")
    } finally {
      setIsActing(false)
    }
  }

  async function handleStop() {
    setIsActing(true)
    try {
      await runtimeApi.stop()
    } catch (e) {
      toast.error(e instanceof Error ? e.message : "Không thể dừng pipeline")
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
      toast.error(e instanceof Error ? e.message : "Không thể khởi động lại pipeline")
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
              <span className="text-sm font-semibold">AI Detection Pipeline</span>
              <Badge variant="outline" className={cn("text-[11px]", s.badgeClass)}>
                {s.label}
              </Badge>
            </div>
            <span className="text-xs text-muted-foreground">{sub}</span>
          </div>
        </div>

        {/* Controls */}
        <div className="flex items-center gap-2">
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

function CameraCell({ camera }: { camera: Camera }) {
  return (
    <Link
      to={`/cameras/${camera.id}`}
      className="relative block aspect-video overflow-hidden rounded-lg ring-1 ring-border transition-shadow hover:ring-2 hover:ring-ring"
    >
      <CameraPreview src={camera.webrtc_address ?? ""} />
      <div className="pointer-events-none absolute bottom-3 left-3 z-30 rounded-md bg-black/60 px-2.5 py-1 text-xs font-medium text-white backdrop-blur-sm">
        {camera.name}
      </div>
    </Link>
  )
}

// ── Event item ────────────────────────────────────────────────────────────────

function EventItem({ event }: { event: (typeof mockEvents)[number] }) {
  const isEnter = event.type === "enter"
  return (
    <div className="flex items-start gap-3 py-2.5">
      <div
        className={cn(
          "mt-0.5 flex size-6 shrink-0 items-center justify-center rounded-full",
          isEnter
            ? "bg-green-500/15 text-green-600 dark:text-green-400"
            : "bg-amber-500/15 text-amber-600 dark:text-amber-400",
        )}
      >
        {isEnter ? <LogIn className="size-3" /> : <LogOut className="size-3" />}
      </div>
      <div className="flex min-w-0 flex-1 flex-col gap-0.5">
        <div className="flex items-center gap-1.5">
          <span className="text-xs font-medium">{event.pid}</span>
          <span
            className={cn(
              "text-[11px]",
              isEnter
                ? "text-green-600 dark:text-green-400"
                : "text-amber-600 dark:text-amber-400",
            )}
          >
            {isEnter ? "vào" : "ra"}
          </span>
          <span className="truncate text-xs text-muted-foreground">{event.zone}</span>
        </div>
        <span className="text-[11px] text-muted-foreground">
          {event.camera} · {event.ts}
        </span>
      </div>
    </div>
  )
}

// ── Page ──────────────────────────────────────────────────────────────────────

export function DashboardPage() {
  const { data: cameras = [], isLoading: camerasLoading } = useCameras()
  const gridCols = cameras.length <= 1 ? "grid-cols-1" : "grid-cols-1 sm:grid-cols-2"

  return (
    <div className="flex flex-col gap-6">

      {/* Pipeline control */}
      <PipelineCard />

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

      {/* Chart + Events */}
      <div className="grid grid-cols-1 gap-6 md:grid-cols-3">

        {/* Hourly detection chart */}
        <Card className="md:col-span-2">
          <CardHeader>
            <CardTitle>Lượt phát hiện theo giờ</CardTitle>
          </CardHeader>
          <CardContent>
            <ResponsiveContainer width="100%" height={200}>
              <AreaChart
                data={mockHourlyData}
                margin={{ top: 4, right: 4, bottom: 0, left: -20 }}
              >
                <defs>
                  <linearGradient id="detectionGrad" x1="0" y1="0" x2="0" y2="1">
                    <stop offset="5%"  stopColor="#3b82f6" stopOpacity={0.3} />
                    <stop offset="95%" stopColor="#3b82f6" stopOpacity={0}   />
                  </linearGradient>
                </defs>
                <CartesianGrid
                  strokeDasharray="3 3"
                  stroke="rgba(128,128,128,0.15)"
                  vertical={false}
                />
                <XAxis
                  dataKey="hour"
                  tick={{ fontSize: 11, fill: "var(--muted-foreground)" }}
                  axisLine={false}
                  tickLine={false}
                />
                <YAxis
                  tick={{ fontSize: 11, fill: "var(--muted-foreground)" }}
                  axisLine={false}
                  tickLine={false}
                  allowDecimals={false}
                />
                <Tooltip
                  separator=": "
                  contentStyle={{
                    backgroundColor: "var(--card)",
                    border: "1px solid var(--border)",
                    borderRadius: "8px",
                    fontSize: 12,
                  }}
                  labelStyle={{ color: "var(--foreground)" }}
                  itemStyle={{ color: "#3b82f6" }}
                  formatter={(value) => [value, "Lượt phát hiện"]}
                />
                <Area
                  type="monotone"
                  dataKey="count"
                  stroke="#3b82f6"
                  strokeWidth={2}
                  fill="url(#detectionGrad)"
                  dot={false}
                  activeDot={{ r: 4, fill: "#3b82f6" }}
                />
              </AreaChart>
            </ResponsiveContainer>
          </CardContent>
        </Card>

        {/* Recent events */}
        <Card className="flex flex-col">
          <CardHeader>
            <CardTitle>Sự kiện gần đây</CardTitle>
          </CardHeader>
          <CardContent className="p-0">
            <ScrollArea className="h-[260px]">
              <div className="flex flex-col divide-y px-4">
                {mockEvents.map((event) => (
                  <EventItem key={event.id} event={event} />
                ))}
              </div>
            </ScrollArea>
          </CardContent>
        </Card>

      </div>
    </div>
  )
}
