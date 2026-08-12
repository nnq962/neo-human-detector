import { useEffect, useRef, useState } from "react"
import type { LucideIcon } from "lucide-react"
import { ChevronDown, Cpu, MemoryStick, Monitor } from "lucide-react"
import { Collapsible } from "radix-ui"
import type { ApiResponse } from "@/api/client"
import { Button } from "@/components/ui/button"
import {
  Popover,
  PopoverContent,
  PopoverDescription,
  PopoverHeader,
  PopoverTitle,
  PopoverTrigger,
} from "@/components/ui/popover"
import { cn } from "@/lib/utils"

type CoreMetric = {
  index: number
  usage_percent: number | null
}

type CpuMetrics = {
  name: string | null
  logical_cores: number | null
  physical_cores: number | null
  usage_percent: number | null
  load_average: number[] | null
  cores?: CoreMetric[]
}

type MemoryMetrics = {
  total_bytes: number | null
  available_bytes: number | null
  used_bytes: number | null
  usage_percent: number | null
}

type GpuMetrics = {
  index: number
  name: string
  kind: "nvidia" | "jetson-integrated" | string
  usage_percent: number | null
  memory_total_bytes: number | null
  memory_used_bytes: number | null
  temperature_celsius: number | null
  power_watts: number | null
}

type HardwareMetrics = {
  collected_at: string
  platform: string
  cpu: CpuMetrics
  memory: MemoryMetrics
  gpus: GpuMetrics[]
}

const RETRY_DELAY_MS = 3000

function getWsUrl(): string {
  const protocol = window.location.protocol === "https:" ? "wss:" : "ws:"
  return `${protocol}//${window.location.host}/ws/metrics`
}

function useHardwareMetrics() {
  const [metrics, setMetrics] = useState<HardwareMetrics | null>(null)
  const [connected, setConnected] = useState(false)
  const socketRef = useRef<WebSocket | null>(null)
  const retryRef = useRef<ReturnType<typeof setTimeout> | null>(null)

  useEffect(() => {
    let disposed = false

    function connect() {
      if (disposed) return
      const socket = new WebSocket(getWsUrl())
      socketRef.current = socket

      socket.onopen = () => {
        if (disposed) {
          socket.close()
          return
        }
        setConnected(true)
      }
      socket.onmessage = (event: MessageEvent) => {
        try {
          const response = JSON.parse(event.data) as ApiResponse<HardwareMetrics>
          if (response.success && response.data) setMetrics(response.data)
        } catch {
          // Bỏ qua payload không đúng định dạng và chờ snapshot kế tiếp.
        }
      }
      socket.onclose = () => {
        if (socketRef.current === socket) socketRef.current = null
        setConnected(false)
        if (!disposed) retryRef.current = setTimeout(connect, RETRY_DELAY_MS)
      }
      socket.onerror = () => socket.close()
    }

    connect()
    return () => {
      disposed = true
      if (retryRef.current) clearTimeout(retryRef.current)
      const socket = socketRef.current
      if (!socket) return
      socket.onmessage = null
      socket.onclose = null
      socket.onerror = null
      if (socket.readyState === WebSocket.CONNECTING) socket.onopen = () => socket.close()
      if (socket.readyState === WebSocket.OPEN) socket.close()
    }
  }, [])

  return { metrics, connected }
}

function formatPercent(value: number | null | undefined): string {
  return value == null ? "—" : `${Math.round(value)}%`
}

function formatBytes(value: number | null | undefined): string {
  if (value == null) return "—"
  const gibibytes = value / 1024 ** 3
  return `${gibibytes >= 10 ? gibibytes.toFixed(0) : gibibytes.toFixed(1)} GB`
}

function MetricBar({
  value,
  indicatorClassName,
}: {
  value: number | null
  indicatorClassName: string
}) {
  return (
    <div className="mt-2 h-1.5 overflow-hidden rounded-full bg-black/10 dark:bg-white/10">
      <div
        className={cn(
          "h-full rounded-full transition-[width] duration-300",
          indicatorClassName,
        )}
        style={{ width: `${Math.max(0, Math.min(100, value ?? 0))}%` }}
      />
    </div>
  )
}

function MetricCard({
  icon: Icon,
  label,
  value,
  detail,
  usage,
  className,
  iconClassName,
  indicatorClassName,
}: {
  icon: LucideIcon
  label: string
  value: string
  detail: string
  usage: number | null
  className: string
  iconClassName: string
  indicatorClassName: string
}) {
  return (
    <div className={cn("rounded-lg border p-3", className)}>
      <div className="flex items-center gap-2">
        <div className={cn(
          "flex size-7 shrink-0 items-center justify-center rounded-md bg-background/80 shadow-sm",
          iconClassName,
        )}>
          <Icon className="size-3.5" />
        </div>
        <div className="min-w-0 flex-1">
          <p className="font-medium">{label}</p>
          <p className="truncate text-xs text-muted-foreground">{value}</p>
        </div>
        <span className="text-sm font-semibold tabular-nums">{formatPercent(usage)}</span>
      </div>
      <MetricBar value={usage} indicatorClassName={indicatorClassName} />
      <p className="mt-1.5 text-xs text-muted-foreground">{detail}</p>
    </div>
  )
}

function CpuCoreUsageGrid({ cores = [] }: { cores?: CoreMetric[] }) {
  const [open, setOpen] = useState(false)

  if (cores.length === 0) return null

  return (
    <Collapsible.Root open={open} onOpenChange={setOpen} asChild>
      <div className="rounded-lg border border-sky-500/20 bg-sky-500/5 dark:bg-sky-500/10">
        <Collapsible.Trigger asChild>
          <button
            type="button"
            className="flex w-full items-center gap-2 rounded-lg p-3 text-left outline-none transition-colors hover:bg-sky-500/5 focus-visible:ring-2 focus-visible:ring-sky-500/40"
          >
            <div className="min-w-0 flex-1">
              <p className="font-medium">Tải từng logical core</p>
              <p className="text-xs text-muted-foreground">{cores.length} cores</p>
            </div>
            <ChevronDown
              className={cn(
                "size-4 shrink-0 text-sky-600 transition-transform duration-200 dark:text-sky-400",
                open && "rotate-180",
              )}
            />
          </button>
        </Collapsible.Trigger>

        <Collapsible.Content className="overflow-hidden data-[state=closed]:animate-collapsible-up data-[state=open]:animate-collapsible-down">
          <div className="grid grid-cols-[repeat(auto-fit,minmax(34px,1fr))] gap-1.5 px-3 pb-3">
            {cores.map((core) => (
              <div key={core.index} className="space-y-1 text-center">
                <div className="flex h-12 items-end overflow-hidden rounded-sm bg-sky-950/10 dark:bg-sky-50/10">
                  <div
                    className="w-full rounded-sm bg-sky-500 transition-[height] duration-300"
                    style={{ height: `${Math.max(0, Math.min(100, core.usage_percent ?? 0))}%` }}
                  />
                </div>
                <p className="text-[10px] leading-none text-muted-foreground">{core.index}</p>
                <p className="text-[10px] leading-none font-medium tabular-nums">
                  {formatPercent(core.usage_percent)}
                </p>
              </div>
            ))}
          </div>
        </Collapsible.Content>
      </div>
    </Collapsible.Root>
  )
}

function GpuMetricCard({ gpu }: { gpu: GpuMetrics }) {
  const hasDedicatedMemory = gpu.memory_total_bytes !== null
  const memoryDetail = hasDedicatedMemory
    ? `${formatBytes(gpu.memory_used_bytes)} / ${formatBytes(gpu.memory_total_bytes)} VRAM`
    : "Bộ nhớ dùng chung với RAM hệ thống"
  const telemetry = [
    gpu.temperature_celsius === null ? null : `${Math.round(gpu.temperature_celsius)}°C`,
    gpu.power_watts === null ? null : `${gpu.power_watts.toFixed(1)} W`,
  ].filter(Boolean).join(" · ")

  return (
    <MetricCard
      icon={Monitor}
      label={gpu.kind === "jetson-integrated" ? "GPU tích hợp" : `GPU ${gpu.index}`}
      value={gpu.name}
      detail={telemetry ? `${memoryDetail} · ${telemetry}` : memoryDetail}
      usage={gpu.usage_percent}
      className="border-violet-500/20 bg-violet-500/5 dark:bg-violet-500/10"
      iconClassName="text-violet-600 dark:text-violet-400"
      indicatorClassName="bg-violet-500"
    />
  )
}

export function HardwareMetricsIndicator() {
  const { metrics, connected } = useHardwareMetrics()
  const cpuUsage = metrics?.cpu.usage_percent ?? null
  const memoryUsage = metrics?.memory.usage_percent ?? null
  const primaryGpu = metrics?.gpus[0]

  return (
    <Popover>
      <PopoverTrigger asChild>
        <Button
          variant="outline"
          size="sm"
          aria-label="Xem thông số phần cứng"
          className={cn(!connected && "text-muted-foreground")}
        >
          <Cpu className="text-muted-foreground" />
          <span className="hidden font-medium tabular-nums sm:inline">CPU {formatPercent(cpuUsage)}</span>
          <span className="hidden h-3.5 w-px bg-border md:block" />
          <span className="hidden items-center gap-1 tabular-nums md:flex">
            <MemoryStick className="size-3.5 text-muted-foreground" />
            RAM {formatPercent(memoryUsage)}
          </span>
          {primaryGpu && (
            <>
              <span className="hidden h-3.5 w-px bg-border lg:block" />
              <span className="hidden items-center gap-1 tabular-nums lg:flex">
                <Monitor className="size-3.5 text-muted-foreground" />
                GPU {formatPercent(primaryGpu.usage_percent)}
              </span>
            </>
          )}
          <ChevronDown className="size-3.5 text-muted-foreground" />
        </Button>
      </PopoverTrigger>

      <PopoverContent align="end" className="w-[min(24rem,calc(100vw-2rem))] p-3">
        <PopoverHeader>
          <div className="flex items-center justify-between gap-3">
            <PopoverTitle>Phần cứng hệ thống</PopoverTitle>
            <span className={cn("size-2 rounded-full", connected ? "bg-green-500" : "bg-muted-foreground")} />
          </div>
          <PopoverDescription className="text-xs">
            {metrics ? metrics.platform : "Đang chờ dữ liệu phần cứng"}
          </PopoverDescription>
        </PopoverHeader>

        {metrics ? (
          <div className="grid gap-2.5">
            <MetricCard
              icon={Cpu}
              label="CPU"
              value={metrics.cpu.name ?? "Không xác định"}
              detail={`${metrics.cpu.physical_cores ?? "—"} physical · ${metrics.cpu.logical_cores ?? "—"} logical · Load ${metrics.cpu.load_average?.[0] ?? "—"}`}
              usage={metrics.cpu.usage_percent}
              className="border-sky-500/20 bg-sky-500/5 dark:bg-sky-500/10"
              iconClassName="text-sky-600 dark:text-sky-400"
              indicatorClassName="bg-sky-500"
            />
            <CpuCoreUsageGrid cores={metrics.cpu.cores} />
            <MetricCard
              icon={MemoryStick}
              label="Bộ nhớ"
              value={`${formatBytes(metrics.memory.used_bytes)} / ${formatBytes(metrics.memory.total_bytes)}`}
              detail={`${formatBytes(metrics.memory.available_bytes)} available`}
              usage={metrics.memory.usage_percent}
              className="border-emerald-500/20 bg-emerald-500/5 dark:bg-emerald-500/10"
              iconClassName="text-emerald-600 dark:text-emerald-400"
              indicatorClassName="bg-emerald-500"
            />
            {metrics.gpus.length > 0 ? (
              metrics.gpus.map((gpu) => <GpuMetricCard key={gpu.index} gpu={gpu} />)
            ) : (
              <div className="rounded-lg border border-dashed p-3 text-xs text-muted-foreground">
                Không phát hiện GPU telemetry trên thiết bị này.
              </div>
            )}
          </div>
        ) : (
          <p className="rounded-lg border border-dashed p-4 text-center text-xs text-muted-foreground">
            Đang kết nối WebSocket `/ws/metrics`…
          </p>
        )}
      </PopoverContent>
    </Popover>
  )
}
