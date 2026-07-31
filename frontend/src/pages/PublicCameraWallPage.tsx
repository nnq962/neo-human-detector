import { useEffect, useMemo, useRef, useState } from "react"
import {
  Camera,
  Check,
  MonitorCog,
  Settings2,
} from "lucide-react"

import neoLogo from "@/assets/NEO.png"
import { CameraPreview } from "@/components/camera-preview"
import { Button } from "@/components/ui/button"
import {
  Sheet,
  SheetContent,
  SheetDescription,
  SheetHeader,
  SheetTitle,
  SheetTrigger,
} from "@/components/ui/sheet"
import { Skeleton } from "@/components/ui/skeleton"
import { Switch } from "@/components/ui/switch"
import { useCameras, type Camera as CameraModel } from "@/hooks/use-cameras"
import { cn } from "@/lib/utils"

const CAMERA_SELECTION_KEY = "neo-public-camera-wall-selection"

function readSavedSelection(): string[] | null {
  try {
    const value = localStorage.getItem(CAMERA_SELECTION_KEY)
    if (value === null) return null
    const parsed = JSON.parse(value)
    return Array.isArray(parsed)
      ? parsed.filter((item): item is string => typeof item === "string")
      : null
  } catch {
    return null
  }
}

function getGridShape(cameraCount: number) {
  if (cameraCount <= 1) return { columns: 1, rows: 1 }
  if (cameraCount === 2) return { columns: 2, rows: 1 }
  if (cameraCount <= 4) return { columns: 2, rows: 2 }
  if (cameraCount <= 6) return { columns: 3, rows: 2 }
  if (cameraCount <= 9) return { columns: 3, rows: 3 }

  const columns = Math.ceil(Math.sqrt(cameraCount * (16 / 9)))
  return { columns, rows: Math.ceil(cameraCount / columns) }
}

function getGridSize(
  hostWidth: number,
  hostHeight: number,
  columns: number,
  rows: number,
  cameraCount: number,
) {
  const gap = 14
  const videoAspectRatio = 16 / 9
  const sizeBoost = 1.15
  const baseWidthScale = cameraCount === 1
    ? 0.7
    : cameraCount === 2
      ? 0.86
      : cameraCount <= 4
        ? 0.84
        : 0.94
  const baseHeightScale = cameraCount === 1
    ? 0.72
    : cameraCount === 2
      ? 0.68
      : cameraCount <= 4
        ? 0.84
        : 0.92
  const widthScale = Math.min(baseWidthScale * sizeBoost, 1)
  const heightScale = Math.min(baseHeightScale * sizeBoost, 1)
  const maxGridWidth = Math.min(
    hostWidth * widthScale,
    cameraCount === 1
      ? 1040 * sizeBoost
      : cameraCount <= 4
        ? 1280 * sizeBoost
        : hostWidth,
  )
  const maxGridHeight = hostHeight * heightScale
  const availableCellWidth = Math.max(
    0,
    (maxGridWidth - gap * (columns - 1)) / columns,
  )
  const availableCellHeight = Math.max(
    0,
    (maxGridHeight - gap * (rows - 1)) / rows,
  )
  const cellWidth = Math.min(
    availableCellWidth,
    availableCellHeight * videoAspectRatio,
  )
  const cellHeight = cellWidth / videoAspectRatio

  return {
    width: cellWidth * columns + gap * (columns - 1),
    height: cellHeight * rows + gap * (rows - 1),
  }
}

function formatClock(date: Date) {
  return date.toLocaleTimeString("vi-VN", {
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
    hour12: false,
  })
}

function CameraWallItem({
  camera,
  className,
}: {
  camera: CameraModel
  className?: string
}) {
  return (
    <article
      className={cn(
        "relative min-h-0 overflow-visible rounded-2xl bg-transparent",
        className,
      )}
    >
      <div
        className="pointer-events-none absolute -inset-[3px] z-20 overflow-hidden rounded-[19px] p-[3px]"
        style={{
          WebkitMask:
            "linear-gradient(#000 0 0) content-box, linear-gradient(#000 0 0)",
          WebkitMaskComposite: "xor",
          maskComposite: "exclude",
        }}
      >
        <div className="absolute -inset-[75%] animate-[spin_6s_linear_infinite] bg-[conic-gradient(from_0deg,transparent_0deg,transparent_205deg,rgba(249,115,22,0.95)_255deg,rgba(13,148,136,0.9)_305deg,rgba(14,116,144,0.82)_335deg,transparent_360deg)] motion-reduce:animate-none" />
      </div>
      <div className="relative z-10 h-full w-full overflow-hidden rounded-2xl">
        <CameraPreview
          src={camera.webrtc_address ?? ""}
          className="bg-transparent"
          zones={camera.zones}
          bboxCameraId={camera.id}
          hideFaceKeypoints
          hideStreamBadges
          videoBorderRadius={16}
        />
      </div>
    </article>
  )
}

function CameraSelector({
  cameras,
  selectedIds,
  onSelectionChange,
}: {
  cameras: CameraModel[]
  selectedIds: string[]
  onSelectionChange: (cameraIds: string[]) => void
}) {
  const enabledCameras = cameras.filter((camera) => camera.enabled)

  const toggleCamera = (cameraId: string, checked: boolean) => {
    const nextIds = checked
      ? [...new Set([...selectedIds, cameraId])]
      : selectedIds.filter((id) => id !== cameraId)
    onSelectionChange(nextIds)
  }

  return (
    <Sheet>
      <SheetTrigger asChild>
        <button
          type="button"
          className="group relative grid size-10 place-items-center overflow-hidden rounded-xl border border-cyan-500/25 bg-white/75 text-cyan-700 shadow-sm backdrop-blur-xl transition hover:border-cyan-500/50 hover:bg-white"
          aria-label="Chọn camera hiển thị"
        >
          <span className="absolute inset-0 translate-y-full bg-linear-to-t from-cyan-400/15 to-transparent transition-transform group-hover:translate-y-0" />
          <Settings2 className="relative size-4.5" />
        </button>
      </SheetTrigger>

      <SheetContent className="border-cyan-500/20 bg-[#f6fbff] text-slate-900 sm:max-w-md">
        <SheetHeader className="border-b border-cyan-950/10 bg-white/75 px-5 py-5">
          <div className="mb-3 grid size-10 place-items-center rounded-xl border border-cyan-500/25 bg-cyan-500/10 text-cyan-700">
            <MonitorCog className="size-5" />
          </div>
          <SheetTitle className="text-lg font-semibold text-slate-900">
            Camera trình chiếu
          </SheetTitle>
          <SheetDescription className="leading-5 text-slate-500">
            Chọn các luồng được phép xuất hiện trên màn hình dành cho khách.
            Thiết lập được lưu trên trình duyệt này.
          </SheetDescription>
        </SheetHeader>

        <div className="flex items-center justify-between border-b border-cyan-950/10 bg-white/50 px-5 py-3">
          <p className="text-xs font-semibold tracking-[0.16em] text-slate-500 uppercase">
            {selectedIds.length}/{enabledCameras.length} đang hiển thị
          </p>
          <div className="flex items-center gap-1">
            <Button
              variant="ghost"
              size="sm"
              className="text-cyan-700 hover:bg-cyan-500/10 hover:text-cyan-800"
              onClick={() => onSelectionChange(enabledCameras.map((camera) => camera.id))}
            >
              Chọn tất cả
            </Button>
            <Button
              variant="ghost"
              size="sm"
              className="text-slate-500 hover:bg-slate-900/5 hover:text-slate-900"
              onClick={() => onSelectionChange([])}
            >
              Bỏ chọn
            </Button>
          </div>
        </div>

        <div className="min-h-0 flex-1 space-y-2 overflow-y-auto px-4 py-4">
          {cameras.map((camera, index) => {
            const checked = camera.enabled && selectedIds.includes(camera.id)
            return (
              <label
                key={camera.id}
                className={cn(
                  "flex cursor-pointer items-center gap-3 rounded-xl border p-3 transition",
                  checked
                    ? "border-cyan-500/35 bg-cyan-500/8 shadow-sm"
                    : "border-slate-200 bg-white/70 hover:border-cyan-500/25 hover:bg-white",
                  !camera.enabled && "cursor-not-allowed opacity-45",
                )}
              >
                <div
                  className={cn(
                    "grid size-9 shrink-0 place-items-center rounded-lg border font-mono text-xs",
                    checked
                      ? "border-cyan-500/30 bg-cyan-500/10 text-cyan-700"
                      : "border-slate-200 bg-slate-50 text-slate-500",
                  )}
                >
                  {checked ? <Check className="size-4" /> : String(index + 1).padStart(2, "0")}
                </div>
                <div className="min-w-0 flex-1">
                  <p className="truncate text-sm font-medium text-slate-900">
                    {camera.name}
                  </p>
                  <p className="mt-0.5 text-[11px] text-slate-500">
                    {camera.enabled ? "Sẵn sàng trình chiếu" : "Camera đang tắt"}
                  </p>
                </div>
                <Switch
                  checked={checked}
                  disabled={!camera.enabled}
                  aria-label={`Hiển thị ${camera.name}`}
                  onCheckedChange={(value) => toggleCamera(camera.id, value)}
                />
              </label>
            )
          })}

          {cameras.length === 0 && (
            <div className="rounded-xl border border-dashed border-slate-300 bg-white/50 px-4 py-10 text-center text-sm text-slate-500">
              Chưa có camera trong hệ thống.
            </div>
          )}
        </div>
      </SheetContent>
    </Sheet>
  )
}

export function PublicCameraWallPage() {
  const { data: cameras = [], isLoading, isError } = useCameras()
  const [selectedIds, setSelectedIds] = useState<string[] | null>(
    readSavedSelection,
  )
  const [now, setNow] = useState(() => new Date())
  const gridHostRef = useRef<HTMLDivElement>(null)
  const [gridHostSize, setGridHostSize] = useState({ width: 0, height: 0 })

  const enabledCameras = useMemo(
    () => cameras.filter((camera) => camera.enabled),
    [cameras],
  )

  useEffect(() => {
    const timer = window.setInterval(() => setNow(new Date()), 1000)
    return () => window.clearInterval(timer)
  }, [])

  useEffect(() => {
    const host = gridHostRef.current
    if (!host) return

    const observer = new ResizeObserver(([entry]) => {
      if (!entry) return
      setGridHostSize({
        width: entry.contentRect.width,
        height: entry.contentRect.height,
      })
    })
    observer.observe(host)
    return () => observer.disconnect()
  }, [])

  const updateSelection = (cameraIds: string[]) => {
    setSelectedIds(cameraIds)
    localStorage.setItem(CAMERA_SELECTION_KEY, JSON.stringify(cameraIds))
  }

  const visibleCameras = enabledCameras.filter((camera) =>
    selectedIds === null || selectedIds.includes(camera.id),
  )
  const gridShape = getGridShape(visibleCameras.length)
  const gridSize = getGridSize(
    gridHostSize.width,
    gridHostSize.height,
    gridShape.columns,
    gridShape.rows,
    visibleCameras.length,
  )

  return (
    <main className="relative flex h-svh min-h-0 flex-col overflow-hidden bg-[#f7fbfc] text-slate-900">
      <div
        className="pointer-events-none absolute inset-0"
        style={{
          background: [
            "radial-gradient(circle at 12% 15%, rgba(34, 211, 238, 0.32), transparent 32%)",
            "radial-gradient(circle at 88% 12%, rgba(59, 130, 246, 0.22), transparent 34%)",
            "radial-gradient(circle at 72% 90%, rgba(251, 146, 60, 0.32), transparent 40%)",
            "linear-gradient(135deg, #f9fdff 0%, #eef8fb 48%, #fff7ed 100%)",
          ].join(", "),
        }}
      />
      <div className="pointer-events-none absolute top-[34%] -left-[12%] h-48 w-[125%] -rotate-6 bg-linear-to-r from-cyan-200/35 via-white/55 to-orange-200/40 blur-[65px]" />
      <div className="pointer-events-none absolute inset-0 opacity-55 [background-image:linear-gradient(rgba(8,145,178,0.07)_1px,transparent_1px),linear-gradient(90deg,rgba(8,145,178,0.07)_1px,transparent_1px)] [background-size:42px_42px]" />

      <header className="relative z-40 flex h-24 shrink-0 items-center gap-4 px-4 sm:px-7 lg:px-10">
        <div className="flex h-13 w-30 shrink-0 items-center justify-center px-2 sm:w-36">
          <img
            src={neoLogo}
            alt="Logo công ty"
            className="h-full w-full object-contain drop-shadow-[0_1px_1px_rgba(15,23,42,0.35)]"
          />
        </div>

        <div className="hidden h-11 w-px bg-slate-900/10 sm:block" />

        <div className="min-w-0">
          <h1 className="truncate text-lg leading-none font-semibold tracking-[-0.03em] text-slate-950 sm:text-2xl">
            NEO{" "}
            <span className="bg-linear-to-r from-[#ff9a2e] via-[#f97316] to-[#dc4f0b] bg-clip-text text-transparent">
              AI VISION
            </span>
          </h1>
          <p className="mt-1.5 hidden truncate text-[9px] font-medium tracking-[0.17em] text-slate-500 uppercase md:block">
            Intelligent perception in real time
          </p>
        </div>

        <div className="mx-3 hidden min-w-16 flex-1 items-center xl:flex">
          <div className="h-px flex-1 bg-linear-to-r from-cyan-500/35 via-blue-500/12 to-transparent" />
          <div className="size-2.5 rotate-45 border border-amber-700/25 bg-white/50" />
          <div className="h-px w-12 bg-amber-700/15" />
        </div>

        <div className="ml-auto hidden items-center gap-3 lg:flex">
          <span className="relative flex size-2">
            <span className="absolute inline-flex size-full animate-ping rounded-full bg-emerald-400 opacity-60" />
            <span className="relative size-2 rounded-full bg-emerald-400" />
          </span>
          <div>
            <p className="text-[8px] font-semibold tracking-[0.2em] text-slate-400 uppercase">
              System status
            </p>
            <p className="mt-0.5 text-[10px] font-bold tracking-[0.16em] text-emerald-700 uppercase">
              Online / Streaming
            </p>
          </div>
        </div>

        <div className="ml-2 border-l border-slate-900/10 pl-4 text-right font-mono tabular-nums">
          <p className="text-sm font-semibold tracking-[0.08em] text-slate-950 sm:text-lg">
            {formatClock(now)}
          </p>
          <p className="hidden text-[9px] tracking-[0.18em] text-slate-500 uppercase sm:block">
            Local time
          </p>
        </div>

        <CameraSelector
          cameras={cameras}
          selectedIds={
            selectedIds ?? enabledCameras.map((camera) => camera.id)
          }
          onSelectionChange={updateSelection}
        />
      </header>

      <section className="relative z-10 flex min-h-0 flex-1 flex-col px-3 pb-5 sm:px-6 sm:pb-7">
        <div className="pointer-events-none absolute top-1/2 left-5 hidden -translate-y-1/2 -rotate-90 items-center gap-3 xl:flex">
          <span className="text-[8px] font-bold tracking-[0.35em] text-cyan-800/45 uppercase">
            Human perception · Spatial intelligence
          </span>
          <span className="h-px w-14 bg-cyan-700/20" />
        </div>
        <div className="pointer-events-none absolute top-1/2 right-5 hidden -translate-y-1/2 rotate-90 items-center gap-3 xl:flex">
          <span className="h-px w-14 bg-amber-800/15" />
          <span className="text-[8px] font-bold tracking-[0.35em] text-amber-900/35 uppercase">
            NEO Robotics · 2026
          </span>
        </div>
        <div className="pointer-events-none absolute top-1/2 left-1/2 size-[62vmin] -translate-x-1/2 -translate-y-1/2 rounded-full border border-cyan-600/6" />
        <div className="pointer-events-none absolute top-1/2 left-1/2 size-[46vmin] -translate-x-1/2 -translate-y-1/2 rounded-full border border-amber-800/5" />

        <div
          ref={gridHostRef}
          className="relative flex min-h-0 flex-1 items-center justify-center"
        >
          {isLoading ? (
            <div className="grid h-full w-full grid-cols-2 gap-3">
              <Skeleton className="rounded-xl bg-cyan-900/10" />
              <Skeleton className="rounded-xl bg-cyan-900/10" />
            </div>
          ) : isError ? (
            <div className="grid h-full w-full place-items-center rounded-xl border border-red-400/25 bg-white/65 shadow-sm backdrop-blur-sm">
              <div className="text-center">
                <Camera className="mx-auto size-8 text-red-500/70" />
                <p className="mt-3 text-sm font-semibold">Không thể tải danh sách camera</p>
                <p className="mt-1 text-xs text-slate-500">Kiểm tra kết nối API và thử tải lại trang.</p>
              </div>
            </div>
          ) : visibleCameras.length === 0 ? (
            <div className="grid h-full w-full place-items-center overflow-hidden rounded-xl border border-dashed border-cyan-500/30 bg-white/65 shadow-sm backdrop-blur-sm">
              <div className="max-w-sm px-6 text-center">
                <div className="mx-auto grid size-14 place-items-center rounded-2xl border border-cyan-500/25 bg-cyan-500/10 text-cyan-700">
                  <Camera className="size-6" />
                </div>
                <p className="mt-4 text-base font-semibold">Chưa chọn camera trình chiếu</p>
                <p className="mt-1.5 text-sm leading-5 text-slate-500">
                  Mở biểu tượng cài đặt ở góc trên bên phải để chọn camera dành cho khách xem.
                </p>
              </div>
            </div>
          ) : (
            <div
              className="grid gap-3.5"
              style={{
                width: gridSize.width,
                height: gridSize.height,
                gridTemplateColumns: `repeat(${gridShape.columns}, minmax(0, 1fr))`,
                gridTemplateRows: `repeat(${gridShape.rows}, minmax(0, 1fr))`,
              }}
            >
              {visibleCameras.map((camera, index) => (
                <CameraWallItem
                  key={camera.id}
                  camera={camera}
                  className={cn(
                    visibleCameras.length === 3
                    && index === visibleCameras.length - 1
                    && "col-span-2 w-[calc(50%-7px)] justify-self-center",
                  )}
                />
              ))}
            </div>
          )}
        </div>
      </section>
    </main>
  )
}
