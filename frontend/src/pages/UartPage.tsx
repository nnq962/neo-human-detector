import { useEffect, useRef, useState } from "react"
import { Pencil, PlugZap, PlugZapIcon, Send, Trash2, X, Check } from "lucide-react"
import { toast } from "sonner"
import { useUartConfig, useInvalidateUart } from "@/hooks/use-uart"
import { useUartEvents, type UartEventsStatus } from "@/hooks/use-uart-events"
import { uartApi, type UartEvent } from "@/api/uart.api"
import { Button } from "@/components/ui/button"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { Input } from "@/components/ui/input"
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select"
import { Skeleton } from "@/components/ui/skeleton"
import { cn } from "@/lib/utils"

const COMMON_PORTS = [
  "/dev/ttyS0", "/dev/ttyS1", "/dev/ttyS2", "/dev/ttyS3", "/dev/ttyS4",
  "/dev/ttyUSB0", "/dev/ttyUSB1", "/dev/ttyUSB2",
  "/dev/ttyAMA0", "/dev/ttyAMA1",
  "/dev/ttyTHS0", "/dev/ttyTHS1", "/dev/ttyTHS2",
]

const COMMON_BAUDRATES = [
  300, 600, 1200, 2400, 4800, 9600, 19200, 38400, 57600,
  115200, 230400, 460800, 921600,
]

// ── Types ──────────────────────────────────────────────────────────────────

interface LogEntry {
  id: number
  ts: string
  raw: string
  type?: UartEvent["type"]
}

const MAX_LOG = 200

// ── UART Config Card ────────────────────────────────────────────────────────

function UartConfigCard() {
  const { data: config, isLoading } = useUartConfig()
  const invalidate = useInvalidateUart()

  const [editing, setEditing]   = useState(false)
  const [port, setPort]         = useState("")
  const [baudrate, setBaudrate] = useState("")
  const [saving, setSaving]     = useState(false)

  function startEdit() {
    setPort(config?.port ?? "")
    setBaudrate(String(config?.baudrate ?? ""))
    setEditing(true)
  }

  function cancelEdit() {
    setEditing(false)
  }

  async function saveEdit() {
    const br = parseInt(baudrate)
    if (!port.trim()) { toast.error("Port không được để trống"); return }
    if (!br || br < 1) { toast.error("Baudrate không hợp lệ"); return }
    setSaving(true)
    try {
      const response = await uartApi.update({ port: port.trim(), baudrate: br })
      toast.success(response.message)
      invalidate()
      setEditing(false)
    } catch (err) {
      toast.error(err instanceof Error ? err.message : "Cập nhật thất bại")
    } finally {
      setSaving(false)
    }
  }

  if (isLoading) return <Skeleton className="h-36" />

  return (
    <Card>
      <CardHeader>
        <div className="flex items-center justify-between">
          <CardTitle>Cấu hình UART</CardTitle>
          {!editing ? (
            <Button variant="outline" size="sm" onClick={startEdit}>
              <Pencil />
              Sửa
            </Button>
          ) : (
            <div className="flex items-center gap-2">
              <Button variant="outline" size="sm" onClick={cancelEdit} disabled={saving}>
                <X />
                Hủy
              </Button>
              <Button size="sm" onClick={saveEdit} disabled={saving}>
                <Check />
                {saving ? "Đang lưu..." : "Lưu"}
              </Button>
            </div>
          )}
        </div>
      </CardHeader>

      <CardContent>
        <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
          {/* Port */}
          <div className="flex flex-col gap-1.5">
            <span className="text-xs text-muted-foreground">Port</span>
            {editing ? (
              <Select value={port} onValueChange={setPort}>
                <SelectTrigger className="h-8 text-sm">
                  <SelectValue placeholder="Chọn port..." />
                </SelectTrigger>
                <SelectContent position="popper" className="w-fit min-w-0">
                  {COMMON_PORTS.map((p) => (
                    <SelectItem key={p} value={p}>{p}</SelectItem>
                  ))}
                </SelectContent>
              </Select>
            ) : (
              <div className="flex h-8 items-center text-sm">{config?.port ?? "—"}</div>
            )}
          </div>

          {/* Baudrate */}
          <div className="flex flex-col gap-1.5">
            <span className="text-xs text-muted-foreground">Baudrate</span>
            {editing ? (
              <Select value={baudrate} onValueChange={setBaudrate}>
                <SelectTrigger className="h-8 text-sm">
                  <SelectValue placeholder="Chọn baudrate..." />
                </SelectTrigger>
                <SelectContent position="popper" className="w-fit min-w-0">
                  {COMMON_BAUDRATES.map((b) => (
                    <SelectItem key={b} value={String(b)}>
                      {b.toLocaleString()}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            ) : (
              <div className="flex h-8 items-center text-sm">{config?.baudrate?.toLocaleString() ?? "—"}</div>
            )}
          </div>
        </div>
      </CardContent>
    </Card>
  )
}

// ── UART Send Card ──────────────────────────────────────────────────────────

function UartSendCard() {
  const [command, setCommand] = useState("")
  const [sending, setSending] = useState(false)

  async function handleSend() {
    const nextCommand = command.trim()
    if (!nextCommand) return

    setSending(true)
    try {
      const result = await uartApi.send(nextCommand)
      toast.success(`Đã gửi: "${result.command}"`)
      setCommand("")
    } catch (err) {
      toast.error(err instanceof Error ? err.message : "Gửi lệnh thất bại")
    } finally {
      setSending(false)
    }
  }

  const SAMPLE_COMMANDS = [
    "PING",
    "STATUS",
    "RESET",
    "MOVE:FORWARD",
    "MOVE:STOP",
    "GOTO:0.0,0.0,0.0",
  ]

  return (
    <Card>
      <CardHeader>
        <CardTitle>Gửi lệnh</CardTitle>
      </CardHeader>
      <CardContent className="flex flex-col gap-3">
        <div className="flex gap-2">
          <Input
            value={command}
            onChange={(e) => setCommand(e.target.value)}
            onKeyDown={(e) => { if (e.key === "Enter") handleSend() }}
            placeholder="Nhập lệnh..."
            disabled={sending}
            className="flex-1"
          />
          <Button onClick={handleSend} disabled={!command.trim() || sending}>
            <Send />
            {sending ? "Đang gửi..." : "Gửi"}
          </Button>
        </div>

        <div className="flex flex-wrap gap-1.5">
          {SAMPLE_COMMANDS.map((cmd) => (
            <button
              key={cmd}
              onClick={() => setCommand(cmd)}
              className="rounded-md border px-2 py-0.5 text-xs text-muted-foreground transition-colors hover:border-foreground/30 hover:text-foreground"
            >
              {cmd}
            </button>
          ))}
        </div>
      </CardContent>
    </Card>
  )
}

// ── UART Monitor Card ───────────────────────────────────────────────────────

function UartMonitorCard() {
  const [log, setLog]         = useState<LogEntry[]>([])
  const terminalRef           = useRef<HTMLDivElement>(null)
  const counterRef            = useRef(0)

  const pushLine = (raw: string, timestamp?: number, type?: UartEvent["type"]) => {
    const date = timestamp ? new Date(timestamp * 1000) : new Date()
    const ts = date.toLocaleTimeString("vi-VN", { hour12: false })
    setLog((prev) => {
      const next = [...prev, { id: ++counterRef.current, ts, raw, type }]
      return next.length > MAX_LOG ? next.slice(next.length - MAX_LOG) : next
    })
  }

  const { status, connect, disconnect } = useUartEvents({
    onEvent: (event) => pushLine(event.raw, event.timestamp, event.type),
    onRawMessage: (message) => pushLine(message),
  })

  function clearLog() {
    setLog([])
  }

  // Auto-scroll only when user is already near the bottom
  useEffect(() => {
    const el = terminalRef.current
    if (!el) return
    const isNearBottom = el.scrollHeight - el.scrollTop - el.clientHeight < 80
    if (isNearBottom) el.scrollTop = el.scrollHeight
  }, [log])

  const statusColor: Record<UartEventsStatus, string> = {
    disconnected: "bg-muted-foreground",
    connecting:   "bg-amber-400",
    connected:    "bg-green-400",
    error:        "bg-red-400",
  }

  const statusLabel: Record<UartEventsStatus, string> = {
    disconnected: "Chưa kết nối",
    connecting:   "Đang kết nối...",
    connected:    "Đang kết nối",
    error:        "Lỗi",
  }

  return (
    <Card className="flex flex-col overflow-hidden">
      <CardHeader>
        <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
          <div className="flex items-center gap-2.5">
            <CardTitle>Dữ liệu nhận</CardTitle>
          </div>

          <div className="flex gap-2">
            <Button
              variant="outline"
              size="sm"
              className="flex-1 sm:flex-none"
              disabled={log.length === 0}
              onClick={clearLog}
            >
              <Trash2 />
              Xóa log
            </Button>

            {status === "connected" || status === "connecting" ? (
              <Button variant="destructive" size="sm" className="flex-1 sm:flex-none" onClick={disconnect}>
                <PlugZapIcon />
                Ngắt kết nối
              </Button>
            ) : (
              <Button size="sm" className="flex-1 sm:flex-none" onClick={connect}>
                <PlugZap />
                Kết nối
              </Button>
            )}
          </div>
        </div>
      </CardHeader>

      <CardContent className="relative p-0">
        {/* Status badge — outside scroll container so it stays fixed */}
        <div className="absolute right-3 top-3 z-20 flex items-center gap-2 rounded-md bg-zinc-800/80 px-2.5 py-1 font-sans text-xs font-medium text-white backdrop-blur-sm">
          <span className="relative flex size-2">
            {status === "connected" && (
              <span className="absolute inline-flex size-full animate-ping rounded-full bg-green-400 opacity-75" />
            )}
            <span className={cn("relative inline-flex size-2 rounded-full", statusColor[status])} />
          </span>
          {statusLabel[status]}
        </div>

        {/* Terminal */}
        <div ref={terminalRef} className="h-[420px] overflow-y-auto border-t bg-zinc-950 dark:bg-zinc-900 font-mono text-xs leading-relaxed
          [&::-webkit-scrollbar]:w-1
          [&::-webkit-scrollbar-track]:bg-transparent
          [&::-webkit-scrollbar-thumb]:rounded-full
          [&::-webkit-scrollbar-thumb]:bg-zinc-700
          hover:[&::-webkit-scrollbar-thumb]:bg-zinc-500"
        >
          {log.length === 0 ? (
            <div className="flex h-full items-center justify-center">
              <p className="text-zinc-500 select-none">
                {status === "disconnected" || status === "error"
                  ? "Nhấn Kết nối để bắt đầu nhận dữ liệu"
                  : "Đang chờ dữ liệu từ UART..."}
              </p>
            </div>
          ) : (
            <div className="p-4 flex flex-col gap-0.5">
              {log.map((entry) => (
                <div key={entry.id} className="flex gap-3 group">
                  <span className="shrink-0 text-zinc-600 select-none">{entry.ts}</span>
                  {entry.type && (
                    <span
                      className={cn(
                        "shrink-0 select-none uppercase",
                        entry.type === "json" ? "text-cyan-400" : "text-amber-300",
                      )}
                    >
                      {entry.type}
                    </span>
                  )}
                  <span className="text-green-400 break-all">{entry.raw}</span>
                </div>
              ))}
            </div>
          )}
        </div>
      </CardContent>
    </Card>
  )
}

// ── Page ────────────────────────────────────────────────────────────────────

export function UartPage() {
  return (
    <div className="flex flex-col gap-6">
      <UartConfigCard />
      <UartSendCard />
      <UartMonitorCard />
    </div>
  )
}
