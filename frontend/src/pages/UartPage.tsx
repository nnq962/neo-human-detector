import { useState } from "react"
import { Check, Pencil, Send, X } from "lucide-react"
import { toast } from "sonner"

import {
  uartApi,
  type UartMessageRequest,
} from "@/api/uart.api"
import { Button } from "@/components/ui/button"
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
  useInvalidateUart,
  useUartConfig,
  useUartStatus,
} from "@/hooks/use-uart"


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
    <Card>
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
            <Button variant="outline" size="sm" onClick={startEdit}>
              <Pencil /> Sửa
            </Button>
          )}
        </div>
      </CardHeader>
      <CardContent className="grid gap-4 sm:grid-cols-2">
        <div className="space-y-1.5">
          <span className="text-xs text-muted-foreground">Port</span>
          {editing ? (
            <Select value={port} onValueChange={setPort}>
              <SelectTrigger><SelectValue placeholder="Chọn port" /></SelectTrigger>
              <SelectContent position="popper" className="w-fit min-w-0">
                {COMMON_PORTS.map((item) => <SelectItem key={item} value={item}>{item}</SelectItem>)}
              </SelectContent>
            </Select>
          ) : <div className="text-sm">{config?.port ?? "—"}</div>}
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
          ) : <div className="text-sm">{config?.baudrate?.toLocaleString() ?? "—"}</div>}
        </div>
      </CardContent>
    </Card>
  )
}


function UartStatusCard() {
  const { data: status, isLoading } = useUartStatus()
  if (isLoading) return <Skeleton className="h-32" />

  return (
    <Card>
      <CardHeader><CardTitle>Trạng thái UART</CardTitle></CardHeader>
      <CardContent className="grid gap-3 text-sm sm:grid-cols-3">
        <div><span className="text-muted-foreground">Protocol: </span>{status?.protocol ?? "v2"}</div>
        <div><span className="text-muted-foreground">Kết nối: </span>{status?.connected ? "Connected" : "Disconnected"}</div>
        <div><span className="text-muted-foreground">Listening: </span>{status?.listening ? "Yes" : "No"}</div>
        {status?.last_error && (
          <div className="text-destructive sm:col-span-3">{status.last_error}</div>
        )}
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
      <UartConfigCard />
      <UartStatusCard />
      <ManualTaskCard />
    </div>
  )
}
