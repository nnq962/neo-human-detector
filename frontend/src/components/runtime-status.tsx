import { useState } from "react"
import { Camera, Check, Cpu, Gauge, Play, RotateCcw, Square, Timer } from "lucide-react"
import { toast } from "sonner"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import {
  Popover,
  PopoverAnchor,
  PopoverContent,
  PopoverTrigger,
} from "@/components/ui/popover"
import { ScrollArea } from "@/components/ui/scroll-area"
import { Spinner } from "@/components/ui/spinner"
import { Switch } from "@/components/ui/switch"
import { runtimeApi, type RuntimeStatus } from "@/api/runtime.api"
import { useCameras } from "@/hooks/use-cameras"
import { useIsMobile } from "@/hooks/use-mobile"
import { useRuntimeConfig, useUpdateRuntimeConfig } from "@/hooks/use-runtime-config"
import { useRuntimeStatus } from "@/hooks/use-runtime-status"
import { cn } from "@/lib/utils"

type RuntimeDisplayState = "running" | "stopped" | "starting" | "stopping" | "error"

const BATCH_OPTIONS = [1, 2, 4] as const

const STATUS_CONFIG: Record<RuntimeDisplayState, { label: string; dotClass: string; badgeClass: string }> = {
  running:  { label: "Đang chạy",     dotClass: "bg-green-500", badgeClass: "border-green-500/30 bg-green-500/10 text-green-600 dark:text-green-400" },
  stopped:  { label: "Đã dừng",       dotClass: "bg-zinc-400",  badgeClass: "border-border bg-muted text-muted-foreground" },
  starting: { label: "Đang khởi động", dotClass: "bg-amber-400", badgeClass: "border-amber-500/30 bg-amber-500/10 text-amber-600 dark:text-amber-400" },
  stopping: { label: "Đang dừng",      dotClass: "bg-amber-400", badgeClass: "border-amber-500/30 bg-amber-500/10 text-amber-600 dark:text-amber-400" },
  error:    { label: "Có lỗi",         dotClass: "bg-red-500",   badgeClass: "border-red-500/30 bg-red-500/10 text-red-600 dark:text-red-400" },
}

function formatUptime(seconds: number): string {
  const days = Math.floor(seconds / 86400)
  const hours = Math.floor(seconds / 3600)
  const hoursInDay = Math.floor((seconds % 86400) / 3600)
  const minutes = Math.floor((seconds % 3600) / 60)
  const remainingSeconds = Math.floor(seconds % 60)
  if (days > 0) return `${days} ngày ${hoursInDay} giờ ${minutes} phút`
  if (hours > 0) return `${hours} giờ ${minutes} phút`
  if (minutes > 0) return `${minutes} phút ${remainingSeconds} giây`
  return `${remainingSeconds} giây`
}

function getStatusSub(displayState: RuntimeDisplayState, status: RuntimeStatus | null): string {
  switch (displayState) {
    case "running":
      return status?.uptime_seconds != null
        ? `Batch ${status.batch_size} · Đã chạy ${formatUptime(status.uptime_seconds)}`
        : `Batch ${status?.batch_size ?? 0} · Đang chạy`
    case "stopped":
      return status?.stopped_at
        ? `Dừng lúc ${new Date(status.stopped_at).toLocaleTimeString("vi-VN", { hour: "2-digit", minute: "2-digit" })}`
        : "Runtime chưa chạy"
    case "error":
      return status?.last_error ?? "Lỗi không xác định"
    case "starting":
      return "Đang mở model và kết nối camera"
    case "stopping":
      return "Đang đóng tài nguyên runtime"
  }
}

function formatInferenceMetric(value: RuntimeStatus["performance"]["yolo"]): string {
  if (value === null) return "Chưa có mẫu"
  return `${value.last_ms.toFixed(1)} ms · TB ${value.average_ms.toFixed(1)} ms`
}

function formatCameraFps(fps: number | null): string {
  return fps === null ? "Chưa có mẫu" : `${fps.toFixed(1)} FPS`
}

function sameCameraIds(left: string[], right: string[]): boolean {
  return left.length === right.length && left.every((value, index) => value === right[index])
}

export function RuntimeStatusIndicator() {
  const isMobile = useIsMobile()
  const { status: runtimeStatus, connected } = useRuntimeStatus()
  const { data: cameras = [], isLoading: camerasLoading } = useCameras()
  const { data: runtimeConfig, isLoading: configLoading } = useRuntimeConfig()
  const updateRuntimeConfig = useUpdateRuntimeConfig()
  const [draftBatchSize, setDraftBatchSize] = useState<number | null>(null)
  const [draftCameraIds, setDraftCameraIds] = useState<string[] | null>(null)
  const [isActing, setIsActing] = useState(false)

  const state = runtimeStatus?.state ?? "stopped"
  const displayState: RuntimeDisplayState = state
  const statusView = STATUS_CONFIG[displayState]
  const transitioning = state === "starting" || state === "stopping"
  const availableCameras = cameras.filter((camera) => camera.enabled)
  const savedCameraIds = runtimeConfig?.camera_ids ?? []
  const selectedCameraIds = draftCameraIds ?? savedCameraIds
  const inferredBatchSize = BATCH_OPTIONS.includes(selectedCameraIds.length as 1 | 2 | 4)
    ? selectedCameraIds.length
    : 1
  const batchSize = draftBatchSize ?? inferredBatchSize
  const selectionValid = selectedCameraIds.length === batchSize
    && selectedCameraIds.every((cameraId) =>
      availableCameras.some((camera) => camera.id === cameraId),
    )
  const selectionChanged = !sameCameraIds(selectedCameraIds, savedCameraIds)
  const settingsDisabled = runtimeStatus?.is_running || transitioning || isActing
  const buttonsDisabled = !connected || transitioning || isActing || configLoading
  const statusSub = runtimeStatus === null && !connected
    ? "Đang kết nối tới server"
    : getStatusSub(displayState, runtimeStatus)

  function changeBatchSize(nextBatchSize: number) {
    setDraftBatchSize(nextBatchSize)
    setDraftCameraIds(selectedCameraIds.slice(0, nextBatchSize))
  }

  function toggleCamera(cameraId: string) {
    if (selectedCameraIds.includes(cameraId)) {
      setDraftCameraIds(selectedCameraIds.filter((value) => value !== cameraId))
      return
    }
    if (selectedCameraIds.length >= batchSize) return
    setDraftCameraIds([...selectedCameraIds, cameraId])
  }

  async function persistSelection() {
    if (!selectionValid) {
      throw new Error(`Vui lòng chọn đúng ${batchSize} camera.`)
    }
    if (!selectionChanged) return
    await updateRuntimeConfig.mutateAsync({ camera_ids: selectedCameraIds })
    setDraftBatchSize(null)
    setDraftCameraIds(null)
  }

  async function handleStart() {
    setIsActing(true)
    try {
      await persistSelection()
      await runtimeApi.start()
    } catch (error) {
      toast.error(error instanceof Error ? error.message : "Không thể khởi động runtime")
    } finally {
      setIsActing(false)
    }
  }

  async function handleStop() {
    setIsActing(true)
    try {
      await runtimeApi.stop()
    } catch (error) {
      toast.error(error instanceof Error ? error.message : "Không thể dừng runtime")
    } finally {
      setIsActing(false)
    }
  }

  async function handleRestart() {
    setIsActing(true)
    try {
      await persistSelection()
      await runtimeApi.restart()
    } catch (error) {
      toast.error(error instanceof Error ? error.message : "Không thể khởi động lại runtime")
    } finally {
      setIsActing(false)
    }
  }

  return (
    <Popover>
      <PopoverTrigger asChild>
        <Button variant="outline" size="sm">
          <span className="relative flex size-3.5 shrink-0 items-center justify-center">
            {transitioning ? (
              <Spinner className="size-3.5 text-muted-foreground" />
            ) : (
              <span className="relative flex size-2.5">
                <span className={cn("absolute inline-flex size-full animate-ping rounded-full opacity-60", statusView.dotClass)} />
                <span className={cn("relative inline-flex size-2.5 rounded-full", statusView.dotClass)} />
              </span>
            )}
          </span>
          <span className="hidden text-xs font-medium sm:inline">{statusView.label}</span>
        </Button>
      </PopoverTrigger>

      {isMobile && (
        <PopoverAnchor className="pointer-events-none fixed top-14 left-1/2 size-px" />
      )}

      <PopoverContent
        align={isMobile ? "center" : "end"}
        sideOffset={8}
        collisionPadding={16}
        className="w-[calc(100vw-2rem)] max-w-96 gap-0 overflow-hidden rounded-2xl border-2 border-border bg-popover p-0 shadow-none ring-0 dark:border-input"
        onInteractOutside={(event) => {
          const target = event.detail.originalEvent.target
          if (target instanceof Element && target.closest("[data-theme-toggle]")) {
            event.preventDefault()
          }
        }}
      >
        <div className="flex items-start gap-3 border-b-2 border-border p-3 sm:p-4 dark:border-input">
          <div className="flex size-10 shrink-0 items-center justify-center rounded-xl bg-[#1cb0f6] text-white">
            <Cpu className="size-5" strokeWidth={2.5} />
          </div>
          <div className="min-w-0 flex-1">
            <div className="flex flex-wrap items-center gap-2">
              <span className="text-sm font-bold">AI Detection Runtime</span>
              <Badge variant="outline" className={cn("text-[10px] uppercase tracking-wide", statusView.badgeClass)}>
                {statusView.label}
              </Badge>
            </div>
            <p className="mt-1 line-clamp-2 text-xs font-medium text-muted-foreground">{statusSub}</p>
          </div>
        </div>

        <ScrollArea className="h-[min(28rem,calc(100vh-5rem))]">
          <div className="flex flex-col gap-4 p-3 sm:p-4">
          <div className="rounded-xl border-2 border-border bg-muted/30 p-3 dark:border-input">
            <div className="flex items-start gap-2">
              <Timer className="mt-0.5 size-4 shrink-0 text-cyan-600 dark:text-cyan-400" />
              <div className="min-w-0 flex-1">
                <p className="text-xs font-bold">Thời gian suy luận model</p>
                <p className="mt-0.5 text-[11px] text-muted-foreground">
                  Mới nhất · trung bình 120 lần chạy gần nhất
                </p>
              </div>
            </div>
            <div className="mt-3 grid gap-2 sm:grid-cols-2">
              <div className="rounded-lg border bg-background px-2.5 py-2">
                <p className="text-[11px] font-medium text-muted-foreground">YOLO / batch</p>
                <p className="mt-0.5 text-xs font-semibold tabular-nums">
                  {formatInferenceMetric(runtimeStatus?.performance.yolo ?? null)}
                </p>
              </div>
              <div className="rounded-lg border bg-background px-2.5 py-2">
                <p className="text-[11px] font-medium text-muted-foreground">ReID / embedding batch</p>
                <p className="mt-0.5 text-xs font-semibold tabular-nums">
                  {formatInferenceMetric(runtimeStatus?.performance.reid ?? null)}
                </p>
              </div>
            </div>
            <div className="mt-3 border-t pt-3">
              <div className="flex items-center gap-2">
                <Gauge className="size-3.5 text-cyan-600 dark:text-cyan-400" />
                <p className="text-[11px] font-medium text-muted-foreground">FPS từng camera</p>
              </div>
              {runtimeStatus?.cameras.length ? (
                <div className="mt-2 grid gap-2 sm:grid-cols-2">
                  {runtimeStatus.cameras.map((camera) => (
                    <div key={camera.id} className="min-w-0 rounded-lg border bg-background px-2.5 py-2">
                      <p className="truncate text-[11px] font-medium text-muted-foreground">{camera.name}</p>
                      <p className="mt-0.5 text-xs font-semibold tabular-nums">{formatCameraFps(camera.fps)}</p>
                    </div>
                  ))}
                </div>
              ) : (
                <p className="mt-2 text-xs text-muted-foreground">Runtime chưa có camera đang chạy.</p>
              )}
            </div>
          </div>

          <div className="space-y-2">
            <div className="flex items-center justify-between">
              <div>
                <p className="text-xs font-bold">Batch xử lý</p>
                <p className="text-[11px] text-muted-foreground">Số camera xử lý đồng thời</p>
              </div>
              <Badge variant="secondary">{selectedCameraIds.length}/{batchSize}</Badge>
            </div>
            <div className="grid grid-cols-3 gap-2">
              {BATCH_OPTIONS.map((option) => (
                <Button
                  key={option}
                  type="button"
                  size="sm"
                  variant={batchSize === option ? "blue" : "outline"}
                  disabled={settingsDisabled || availableCameras.length < option}
                  aria-pressed={batchSize === option}
                  onClick={() => changeBatchSize(option)}
                >
                  {option}
                </Button>
              ))}
            </div>
          </div>

          <div className="space-y-2">
            <div>
              <p className="text-xs font-bold">Camera tham gia</p>
              <p className="text-[11px] text-muted-foreground">Chọn đúng {batchSize} camera để chạy AI</p>
            </div>
            {camerasLoading ? (
              <Button variant="outline" className="w-full justify-start" disabled>
                <Spinner /> Đang tải camera...
              </Button>
            ) : availableCameras.length === 0 ? (
              <div className="rounded-xl border border-dashed p-3 text-center text-xs text-muted-foreground">
                Chưa có camera sẵn sàng.
              </div>
            ) : (
              <div className="rounded-xl border-2 border-border bg-muted/10 p-1.5 dark:border-input">
                <div className="space-y-1.5">
                  {availableCameras.map((camera) => {
                    const selected = selectedCameraIds.includes(camera.id)
                    const selectionFull = !selected && selectedCameraIds.length >= batchSize
                    return (
                      <button
                        key={camera.id}
                        type="button"
                        className={cn(
                          "flex w-full items-center gap-3 rounded-lg border-2 px-3 py-2 text-left transition-colors",
                          selected
                            ? "border-cyan-500/50 bg-cyan-500/10"
                            : "border-transparent bg-background/70 hover:bg-muted",
                          (settingsDisabled || selectionFull) && "cursor-not-allowed opacity-50",
                        )}
                        disabled={Boolean(settingsDisabled || selectionFull)}
                        aria-pressed={selected}
                        onClick={() => toggleCamera(camera.id)}
                      >
                        <Camera className="size-4 shrink-0 text-muted-foreground" />
                        <span className="min-w-0 flex-1 truncate text-xs font-medium">
                          {camera.name}
                        </span>
                        <span className={cn(
                          "grid size-5 shrink-0 place-items-center rounded-md border-2",
                          selected
                            ? "border-cyan-600 bg-cyan-600 text-white"
                            : "border-muted-foreground/35",
                        )}>
                          {selected && <Check className="size-3.5" />}
                        </span>
                      </button>
                    )
                  })}
                </div>
              </div>
            )}
          </div>

          <div className="flex items-center justify-between gap-3 rounded-xl border-2 border-border bg-muted/30 px-3 py-2.5 dark:border-input">
            <div>
              <p className="text-xs font-bold">Tự động khởi động</p>
              <p className="mt-0.5 text-[11px] text-muted-foreground">Chạy cấu hình này khi server sẵn sàng</p>
            </div>
            <Switch
              className="runtime-auto-start-switch"
              checked={runtimeConfig?.auto_start ?? false}
              disabled={configLoading || updateRuntimeConfig.isPending || (!selectionValid && !runtimeConfig?.auto_start)}
              onCheckedChange={(autoStart) => {
                updateRuntimeConfig.mutate(
                  {
                    auto_start: autoStart,
                    ...(selectionValid ? { camera_ids: selectedCameraIds } : {}),
                  },
                  {
                    onSuccess: () => {
                      if (selectionValid) {
                        setDraftBatchSize(null)
                        setDraftCameraIds(null)
                      }
                    },
                    onError: (error) => {
                      toast.error(error instanceof Error ? error.message : "Không thể cập nhật tự động khởi động")
                    },
                  },
                )
              }}
            />
          </div>

          <div className="grid grid-cols-3 gap-2">
            <Button
              size="sm"
              disabled={buttonsDisabled || runtimeStatus?.is_running || !selectionValid}
              onClick={handleStart}
            >
              <Play />
              Start
            </Button>
            <Button
              size="sm"
              variant="destructive"
              disabled={buttonsDisabled || !runtimeStatus?.is_running}
              onClick={handleStop}
            >
              <Square />
              Stop
            </Button>
            <Button
              size="sm"
              variant="outline"
              disabled={buttonsDisabled || !runtimeStatus?.is_running || !selectionValid}
              onClick={handleRestart}
            >
              <RotateCcw />
              Restart
            </Button>
          </div>
          </div>
        </ScrollArea>
      </PopoverContent>
    </Popover>
  )
}
