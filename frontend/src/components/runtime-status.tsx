import { useEffect, useState } from "react"
import { Cpu, Play, RotateCcw, Square } from "lucide-react"
import { toast } from "sonner"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { Popover, PopoverContent, PopoverTrigger } from "@/components/ui/popover"
import { Spinner } from "@/components/ui/spinner"
import { Switch } from "@/components/ui/switch"
import { runtimeApi, type RuntimeStatus } from "@/api/runtime.api"
import { useAutoStartConfig, useUpdateAutoStartConfig } from "@/hooks/use-auto-start"
import { useRuntimeStatus } from "@/hooks/use-runtime-status"
import { cn } from "@/lib/utils"

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

export function RuntimeStatusIndicator() {
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
    <Popover>
      <PopoverTrigger asChild>
        <Button variant="outline">
          <span className="relative flex size-3.5 shrink-0 items-center justify-center">
            {transitioning ? (
              <Spinner className="size-3.5 text-muted-foreground" />
            ) : (
              <span className="relative flex size-2.5">
                <span className={cn("absolute inline-flex size-full animate-ping rounded-full opacity-60", s.dotClass)} />
                <span className={cn("relative inline-flex size-2.5 rounded-full", s.dotClass)} />
              </span>
            )}
          </span>
          <span className="text-xs font-medium">{s.label}</span>
        </Button>
      </PopoverTrigger>

      <PopoverContent
        align="end"
        sideOffset={8}
        className="w-80 gap-0 overflow-hidden rounded-2xl border-2 border-border bg-popover p-0 shadow-none ring-0 dark:border-input"
        onInteractOutside={(event) => {
          const target = event.detail.originalEvent.target

          if (target instanceof Element && target.closest("[data-theme-toggle]")) {
            event.preventDefault()
          }
        }}
      >

          {/* Status */}
        <div className="flex items-start gap-3 border-b-2 border-border p-4 dark:border-input">
          <div className="flex size-10 shrink-0 items-center justify-center rounded-xl bg-[#1cb0f6] text-white">
            <Cpu className="size-5" strokeWidth={2.5} />
          </div>
          <div className="min-w-0 flex-1">
            <div className="flex flex-wrap items-center gap-2">
              <span className="text-sm font-bold">AI Detection Runtime</span>
              <Badge
                variant="outline"
                className={cn("text-[10px] uppercase tracking-wide", s.badgeClass)}
              >
                {s.label}
              </Badge>
            </div>
            <p className="mt-1 text-xs font-medium text-muted-foreground">{sub}</p>
          </div>
        </div>

        <div className="flex flex-col gap-4 p-4">
          {/* Auto start */}
          <div className="flex items-center justify-between gap-3 rounded-xl border-2 border-border bg-muted/30 px-3 py-2.5 dark:border-input">
            <div>
              <p className="text-xs font-bold">Tự động khởi động</p>
              <p className="mt-0.5 text-[11px] text-muted-foreground">
                Chạy runtime khi server sẵn sàng
              </p>
            </div>
            <Switch
              className="runtime-auto-start-switch"
              checked={autoStart}
              disabled={updateAutoStart.isPending}
              onCheckedChange={(checked) => {
                updateAutoStart.mutate(
                  { auto_start: checked },
                  {
                    onError: (e) => {
                      toast.error(e instanceof Error ? e.message : "Không thể cập nhật auto start")
                    },
                  },
                )
              }}
            />
          </div>

          {/* Controls */}
          <div className="grid grid-cols-3 gap-2">
            <Button
              size="sm"
              disabled={buttonsDisabled || displayState === "running"}
              onClick={handleStart}
            >
              <Play />
              Start
            </Button>
            <Button
              size="sm"
              variant="destructive"
              disabled={buttonsDisabled || displayState === "stopped"}
              onClick={handleStop}
            >
              <Square />
              Stop
            </Button>
            <Button
              size="sm"
              variant="outline"
              disabled={buttonsDisabled || displayState === "stopped"}
              onClick={handleRestart}
            >
              <RotateCcw />
              Restart
            </Button>
          </div>
        </div>

      </PopoverContent>
    </Popover>
  )
}
