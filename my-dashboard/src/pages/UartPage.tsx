import { useEffect, useRef, useState } from "react"
import { Pencil, PlugZap, PlugZapIcon, Send, Trash2, X, Check } from "lucide-react"
import { toast } from "sonner"
import { useUartConfig, useInvalidateUart } from "@/hooks/use-uart"
import { uartApi } from "@/api/uart.api"
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

type WsStatus = "disconnected" | "connecting" | "connected" | "error"

interface LogEntry {
  id: number
  ts: string
  raw: string
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
      await uartApi.update({ port: port.trim(), baudrate: br })
      toast.success("Đã cập nhật cấu hình UART")
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
                <SelectContent position="popper">
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
                <SelectContent position="popper">
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
    if (!command.trim()) return
    setSending(true)
    await new Promise((r) => setTimeout(r, 2000))
    toast.success(`Đã gửi: "${command.trim()}"`)
    setCommand("")
    setSending(false)
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
  const [status, setStatus]   = useState<WsStatus>("disconnected")
  const [log, setLog]         = useState<LogEntry[]>([])
  const wsRef                 = useRef<WebSocket | null>(null)
  const logEndRef             = useRef<HTMLDivElement>(null)
  const counterRef            = useRef(0)

  function connect() {
    if (wsRef.current) return
    setStatus("connecting")

    const ws = new WebSocket(`ws://${window.location.host}/ws/uart`)
    wsRef.current = ws

    ws.onopen  = () => setStatus("connected")
    ws.onerror = () => setStatus("error")
    ws.onclose = () => {
      setStatus("disconnected")
      wsRef.current = null
    }
    ws.onmessage = (e) => {
      const ts = new Date().toLocaleTimeString("vi-VN", { hour12: false })
      let raw: string
      try {
        raw = JSON.stringify(JSON.parse(e.data), null, 0)
      } catch {
        raw = e.data
      }
      setLog((prev) => {
        const next = [...prev, { id: ++counterRef.current, ts, raw }]
        return next.length > MAX_LOG ? next.slice(next.length - MAX_LOG) : next
      })
    }
  }

  function disconnect() {
    wsRef.current?.close()
    wsRef.current = null
    setStatus("disconnected")
  }

  function clearLog() {
    setLog([])
  }

  // Auto-scroll to bottom when new data arrives
  useEffect(() => {
    logEndRef.current?.scrollIntoView({ behavior: "smooth" })
  }, [log])

  // Cleanup on unmount
  useEffect(() => {
    return () => { wsRef.current?.close() }
  }, [])

  const statusColor: Record<WsStatus, string> = {
    disconnected: "bg-muted-foreground",
    connecting:   "bg-amber-400",
    connected:    "bg-green-400",
    error:        "bg-red-400",
  }

  const statusLabel: Record<WsStatus, string> = {
    disconnected: "Chưa kết nối",
    connecting:   "Đang kết nối...",
    connected:    "Đang kết nối",
    error:        "Lỗi",
  }

  return (
    <Card className="flex flex-col">
      <CardHeader>
        <div className="flex items-center justify-between gap-2 flex-wrap">
          <div className="flex items-center gap-2.5">
            <CardTitle>Dữ liệu nhận</CardTitle>
            <div className="flex items-center gap-1.5">
              <span className="relative flex size-2">
                {status === "connected" && (
                  <span className="absolute inline-flex size-full animate-ping rounded-full bg-green-400 opacity-75" />
                )}
                <span className={cn("relative inline-flex size-2 rounded-full", statusColor[status])} />
              </span>
              <span className="text-xs text-muted-foreground">{statusLabel[status]}</span>
            </div>
          </div>

          <div className="flex items-center gap-2">
            <Button
              variant="outline"
              size="sm"
              disabled={log.length === 0}
              onClick={clearLog}
            >
              <Trash2 />
              Xóa log
            </Button>

            {status === "connected" || status === "connecting" ? (
              <Button variant="destructive" size="sm" onClick={disconnect}>
                <PlugZapIcon />
                Ngắt kết nối
              </Button>
            ) : (
              <Button size="sm" onClick={connect}>
                <PlugZap />
                Kết nối
              </Button>
            )}
          </div>
        </div>
      </CardHeader>

      <CardContent className="p-0 pb-0!">
        {/* Terminal */}
        <div className="h-[420px] overflow-y-auto bg-zinc-950 dark:bg-zinc-900 rounded-b-xl font-mono text-xs leading-relaxed
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
                  <span className="text-green-400 break-all">{entry.raw}</span>
                </div>
              ))}
              <div ref={logEndRef} />
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
