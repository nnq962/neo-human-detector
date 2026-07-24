import { useState } from "react"
import { Activity, Bot, Check, Clock3, Pencil, Send, X } from "lucide-react"
import { toast } from "sonner"

import {
  uartApi,
  type UartMessageRequest,
} from "@/api/uart.api"
import { Button } from "@/components/ui/button"
import { Badge } from "@/components/ui/badge"
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card"
import { Input } from "@/components/ui/input"
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select"
import { Skeleton } from "@/components/ui/skeleton"
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table"
import {
  useInvalidateUart,
  useUartConfig,
  useUartStatus,
} from "@/hooks/use-uart"
import { useRobotHeartbeats } from "@/hooks/use-robot-heartbeats"
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

const NUMBER_INPUT_CLASS =
  "[appearance:textfield] [&::-webkit-inner-spin-button]:appearance-none [&::-webkit-outer-spin-button]:appearance-none"

const ROBOT_STATE_VIEW = {
  IDLE: {
    label: "IDLE",
    className: "border-emerald-500/30 bg-emerald-500/10 text-emerald-700 dark:text-emerald-400",
  },
  SERVING: {
    label: "SERVING",
    className: "border-blue-500/30 bg-blue-500/10 text-blue-700 dark:text-blue-400",
  },
  ERROR: {
    label: "ERROR",
    className: "border-red-500/30 bg-red-500/10 text-red-700 dark:text-red-400",
  },
  UNKNOWN: {
    label: "UNKNOWN",
    className: "border-zinc-500/30 bg-zinc-500/10 text-zinc-700 dark:text-zinc-400",
  },
}


function UartConfigCard() {
  const { data: config, isLoading } = useUartConfig()
  const invalidate = useInvalidateUart()
  const [editing, setEditing] = useState(false)
  const [port, setPort] = useState("")
  const [baudrate, setBaudrate] = useState("")
  const [saving, setSaving] = useState(false)

  function startEdit() {
    setPort(config?.port ?? "")
    setBaudrate(String(config?.baudrate ?? ""))
    setEditing(true)
  }

  async function saveEdit() {
    const nextBaudrate = Number.parseInt(baudrate)
    if (!port.trim() || !nextBaudrate) {
      toast.error("Cấu hình UART không hợp lệ")
      return
    }

    setSaving(true)
    try {
      const response = await uartApi.update({
        port: port.trim(),
        baudrate: nextBaudrate,
      })
      toast.success(response.message)
      await invalidate()
      setEditing(false)
    } catch (error) {
      toast.error(error instanceof Error ? error.message : "Cập nhật thất bại")
    } finally {
      setSaving(false)
    }
  }

  if (isLoading) return <Skeleton className="h-36" />

  return (
    <Card className="@container">
      <CardHeader>
        <div className="flex items-center justify-between">
          <CardTitle>Cấu hình UART V2</CardTitle>
          {editing ? (
            <div className="flex gap-2">
              <Button variant="outline" size="sm" onClick={() => setEditing(false)} disabled={saving}>
                <X /> Hủy
              </Button>
              <Button size="sm" onClick={saveEdit} disabled={saving}>
                <Check /> {saving ? "Đang lưu..." : "Lưu"}
              </Button>
            </div>
          ) : (
            <Button variant="blue" size="sm" onClick={startEdit}>
              <Pencil /> Sửa
            </Button>
          )}
        </div>
      </CardHeader>
      <CardContent className="grid gap-4 @sm:grid-cols-2">
        <div className="space-y-1.5">
          <span className="text-xs text-muted-foreground">Port</span>
          {editing ? (
            <Select value={port} onValueChange={setPort}>
              <SelectTrigger><SelectValue placeholder="Chọn port" /></SelectTrigger>
              <SelectContent position="popper" className="w-fit min-w-0">
                {COMMON_PORTS.map((item) => <SelectItem key={item} value={item}>{item}</SelectItem>)}
              </SelectContent>
            </Select>
          ) : <div className="flex h-8 items-center text-sm">{config?.port ?? "—"}</div>}
        </div>
        <div className="space-y-1.5">
          <span className="text-xs text-muted-foreground">Baudrate</span>
          {editing ? (
            <Select value={baudrate} onValueChange={setBaudrate}>
              <SelectTrigger><SelectValue placeholder="Chọn baudrate" /></SelectTrigger>
              <SelectContent position="popper" className="w-fit min-w-0">
                {COMMON_BAUDRATES.map((item) => (
                  <SelectItem key={item} value={String(item)}>{item.toLocaleString()}</SelectItem>
                ))}
              </SelectContent>
            </Select>
          ) : <div className="flex h-8 items-center text-sm">{config?.baudrate?.toLocaleString() ?? "—"}</div>}
        </div>
      </CardContent>
    </Card>
  )
}


function UartStatusCard() {
  const { data: status, isLoading } = useUartStatus()
  if (isLoading) return <Skeleton className="h-32" />

  return (
    <Card className="@container">
      <CardHeader><CardTitle>Trạng thái UART</CardTitle></CardHeader>
      <CardContent className="grid gap-3 text-sm @sm:grid-cols-3">
        <div><span className="text-muted-foreground">Protocol: </span>{status?.protocol ?? "v2"}</div>
        <div><span className="text-muted-foreground">Kết nối: </span>{status?.connected ? "Connected" : "Disconnected"}</div>
        <div><span className="text-muted-foreground">Listening: </span>{status?.listening ? "Yes" : "No"}</div>
        {status?.last_error && (
          <div className="text-destructive @sm:col-span-3">{status.last_error}</div>
        )}
      </CardContent>
    </Card>
  )
}


function RobotHeartbeatCard() {
  const { snapshot, connected } = useRobotHeartbeats()
  const robots = snapshot?.robots ?? []
  const latestHeartbeatSeconds = snapshot?.latest_heartbeat_age_seconds

  return (
    <Card>
      <CardHeader>
        <div className="flex flex-wrap items-start justify-between gap-3">
          <div className="space-y-1">
            <CardTitle>Robot & Heartbeat</CardTitle>
            <CardDescription>
              Tổng quan robot và gói Heartbeat mới nhất nhận qua UART V2.
            </CardDescription>
          </div>
          <Badge variant={connected ? "secondary" : "outline"} className="gap-1.5">
            <span className="relative flex size-2">
              <span
                className={`absolute inline-flex size-full animate-ping rounded-full opacity-75 ${connected ? "bg-emerald-500" : "bg-amber-500"}`}
              />
              <span
                className={`relative inline-flex size-2 rounded-full ${connected ? "bg-emerald-500" : "bg-amber-500"}`}
              />
            </span>
            {connected ? "Đang cập nhật" : "Đang kết nối"}
          </Badge>
        </div>
      </CardHeader>

      <CardContent className="space-y-4">
        <div className="grid gap-3 sm:grid-cols-3">
          <div className="flex items-center gap-3 rounded-lg border bg-muted/30 p-3">
            <div className="flex size-9 items-center justify-center rounded-md bg-background ring-1 ring-border">
              <Bot className="size-4 text-violet-500" />
            </div>
            <div>
              <p className="text-xs text-muted-foreground">Tổng robot</p>
              <p className="text-lg font-semibold leading-tight">{snapshot?.total ?? 0}</p>
            </div>
          </div>

          <div className="flex items-center gap-3 rounded-lg border bg-muted/30 p-3">
            <div className="flex size-9 items-center justify-center rounded-md bg-background ring-1 ring-border">
              <Activity className="size-4 text-emerald-500" />
            </div>
            <div>
              <p className="text-xs text-muted-foreground">Đang online</p>
              <p className="text-lg font-semibold leading-tight">
                {snapshot?.online ?? 0}/{snapshot?.total ?? 0}
              </p>
            </div>
          </div>

          <div className="flex items-center gap-3 rounded-lg border bg-muted/30 p-3">
            <div className="flex size-9 items-center justify-center rounded-md bg-background ring-1 ring-border">
              <Clock3 className="size-4 text-blue-500" />
            </div>
            <div>
              <p className="text-xs text-muted-foreground">Heartbeat gần nhất</p>
              <p className="text-lg font-semibold leading-tight">
                {latestHeartbeatSeconds == null
                  ? "Chưa nhận"
                  : `${Math.floor(latestHeartbeatSeconds)}s trước`}
              </p>
            </div>
          </div>
        </div>

        <div className="overflow-hidden rounded-lg border">
          <Table className="table-fixed">
            <TableHeader className="bg-muted/40">
              <TableRow>
                <TableHead className="w-40">Robot</TableHead>
                <TableHead className="w-28">Trạng thái</TableHead>
                <TableHead className="w-40">Heartbeat</TableHead>
                <TableHead className="w-56">Pose</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {robots.map((robot) => {
                const stateView = ROBOT_STATE_VIEW[robot.state]

                return (
                  <TableRow key={robot.robot_id}>
                    <TableCell>
                      <div className="flex items-center gap-2">
                        <span
                          className={`size-2 rounded-full ${robot.online ? "bg-emerald-500" : "bg-zinc-400"}`}
                        />
                        <span className="truncate font-medium">Robot #{robot.robot_id}</span>
                      </div>
                    </TableCell>
                    <TableCell>
                      <Badge variant="outline" className={stateView.className}>
                        {stateView.label}
                      </Badge>
                    </TableCell>
                    <TableCell>
                      <div className="space-y-0.5">
                        <p className="truncate">{new Date(robot.heartbeat_timestamp * 1000).toLocaleTimeString("vi-VN", { hour12: false })}</p>
                        <p className={cn("truncate", robot.online ? "text-xs text-emerald-600" : "text-xs text-muted-foreground")}>
                          {Math.floor(robot.heartbeat_age_seconds)} giây trước
                        </p>
                      </div>
                    </TableCell>
                    <TableCell>
                      <div className="flex items-center gap-1.5">
                        <Badge variant="secondary" className="font-normal tabular-nums">
                          {robot.x.toFixed(2)}
                        </Badge>
                        <Badge variant="secondary" className="font-normal tabular-nums">
                          {robot.y.toFixed(2)}
                        </Badge>
                        <Badge variant="secondary" className="font-normal tabular-nums">
                          {robot.theta.toFixed(2)}
                        </Badge>
                      </div>
                    </TableCell>
                  </TableRow>
                )
              })}
              {robots.length === 0 && (
                <TableRow>
                  <TableCell colSpan={4} className="h-24 text-center text-muted-foreground">
                    Chưa nhận được Heartbeat từ robot.
                  </TableCell>
                </TableRow>
              )}
            </TableBody>
          </Table>
        </div>
      </CardContent>
    </Card>
  )
}


function ManualTaskCard() {
  const invalidate = useInvalidateUart()
  const [messageType, setMessageType] = useState<"task_assign" | "task_cancel">("task_assign")
  const [robotId, setRobotId] = useState("1")
  const [taskId, setTaskId] = useState("0")
  const [x, setX] = useState("0")
  const [y, setY] = useState("0")
  const [theta, setTheta] = useState("0")
  const [sending, setSending] = useState(false)

  async function sendMessage() {
    const base = {
      robot_id: Number(robotId),
      task_id: Number(taskId),
    }
    const request: UartMessageRequest = messageType === "task_assign"
      ? {
          message_type: "task_assign",
          ...base,
          x: Number(x),
          y: Number(y),
          theta: Number(theta),
        }
      : { message_type: "task_cancel", ...base }

    setSending(true)
    try {
      const result = await uartApi.sendMessage(request)
      toast.success(`${result.message_type} đã nhận ACK`)
      await invalidate()
    } catch (error) {
      toast.error(error instanceof Error ? error.message : "Gửi message thất bại")
    } finally {
      setSending(false)
    }
  }

  return (
    <Card>
      <CardHeader>
        <CardTitle>Gửi task thủ công</CardTitle>
        <CardDescription>
          Chỉ dùng khi vision Runtime đã dừng. Task Assign tạo task mới,
          Task Cancel hủy task thủ công đã gửi trước đó.
        </CardDescription>
      </CardHeader>
      <CardContent className="space-y-4">
        <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
          <div className="space-y-1.5">
            <label className="text-xs font-medium">Loại message</label>
            <Select value={messageType} onValueChange={(value) => setMessageType(value as typeof messageType)}>
              <SelectTrigger><SelectValue /></SelectTrigger>
              <SelectContent position="popper" className="w-fit min-w-0">
                <SelectItem value="task_assign">Task Assign</SelectItem>
                <SelectItem value="task_cancel">Task Cancel</SelectItem>
              </SelectContent>
            </Select>
            <p className="text-xs text-muted-foreground">
              Chọn giao task mới hoặc hủy task đang theo dõi.
            </p>
          </div>

          <div className="space-y-1.5">
            <label htmlFor="manual-robot-id" className="text-xs font-medium">Robot ID</label>
            <Input
              id="manual-robot-id"
              type="number"
              min={0}
              max={255}
              className={NUMBER_INPUT_CLASS}
              value={robotId}
              onChange={(event) => setRobotId(event.target.value)}
              onWheel={(event) => event.currentTarget.blur()}
            />
            <p className="text-xs text-muted-foreground">
              ID robot nhận lệnh, giá trị từ 0 đến 255.
            </p>
          </div>

          <div className="space-y-1.5">
            <label htmlFor="manual-task-id" className="text-xs font-medium">Task ID</label>
            <Input
              id="manual-task-id"
              type="number"
              min={0}
              max={255}
              className={NUMBER_INPUT_CLASS}
              value={taskId}
              onChange={(event) => setTaskId(event.target.value)}
              onWheel={(event) => event.currentTarget.blur()}
            />
            <p className="text-xs text-muted-foreground">
              ID task từ 0–255; khi cancel phải trùng task đã assign.
            </p>
          </div>

          {messageType === "task_assign" && (
            <>
              <div className="space-y-1.5">
                <label htmlFor="manual-goal-x" className="text-xs font-medium">Goal X</label>
                <Input
                  id="manual-goal-x"
                  type="number"
                  step="any"
                  className={NUMBER_INPUT_CLASS}
                  value={x}
                  onChange={(event) => setX(event.target.value)}
                  onWheel={(event) => event.currentTarget.blur()}
                />
                <p className="text-xs text-muted-foreground">
                  Tọa độ X của điểm đến, đơn vị mét.
                </p>
              </div>

              <div className="space-y-1.5">
                <label htmlFor="manual-goal-y" className="text-xs font-medium">Goal Y</label>
                <Input
                  id="manual-goal-y"
                  type="number"
                  step="any"
                  className={NUMBER_INPUT_CLASS}
                  value={y}
                  onChange={(event) => setY(event.target.value)}
                  onWheel={(event) => event.currentTarget.blur()}
                />
                <p className="text-xs text-muted-foreground">
                  Tọa độ Y của điểm đến, đơn vị mét.
                </p>
              </div>

              <div className="space-y-1.5">
                <label htmlFor="manual-goal-theta" className="text-xs font-medium">Goal Theta</label>
                <Input
                  id="manual-goal-theta"
                  type="number"
                  step="any"
                  className={NUMBER_INPUT_CLASS}
                  value={theta}
                  onChange={(event) => setTheta(event.target.value)}
                  onWheel={(event) => event.currentTarget.blur()}
                />
                <p className="text-xs text-muted-foreground">
                  Góc hướng cuối của robot, đơn vị radian.
                </p>
              </div>
            </>
          )}
        </div>
        <Button onClick={sendMessage} disabled={sending}>
          <Send /> {sending ? "Đang chờ ACK..." : "Gửi message"}
        </Button>
      </CardContent>
    </Card>
  )
}


export function UartPage() {
  return (
    <div className="flex flex-col gap-6">
      <div className="grid grid-cols-1 gap-6 md:grid-cols-2">
        <UartConfigCard />
        <UartStatusCard />
      </div>
      <RobotHeartbeatCard />
      <ManualTaskCard />
    </div>
  )
}
