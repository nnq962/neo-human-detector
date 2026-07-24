import { useState } from "react"
import { Activity, Bot, Check, Clock3, Pencil, Send, Shuffle, X } from "lucide-react"
import { toast } from "sonner"

import {
  type RobotHeartbeat,
  type RobotHeartbeatSnapshot,
  uartApi,
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

function generateMoveId(previous?: number) {
  let moveId = Math.floor(Math.random() * 256)
  while (moveId === previous) {
    moveId = Math.floor(Math.random() * 256)
  }
  return moveId
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


function RobotHeartbeatCard({
  snapshot,
  connected,
}: {
  snapshot: RobotHeartbeatSnapshot | null
  connected: boolean
}) {
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


function MoveToPointCard({ robots }: { robots: RobotHeartbeat[] }) {
  const invalidate = useInvalidateUart()
  const [robotId, setRobotId] = useState("")
  const [moveId, setMoveId] = useState(() => generateMoveId())
  const [x, setX] = useState("0")
  const [y, setY] = useState("0")
  const [theta, setTheta] = useState("0")
  const [sending, setSending] = useState(false)
  const onlineRobots = robots.filter((robot) => robot.online)
  const selectedRobotId = onlineRobots.some(
    (robot) => String(robot.robot_id) === robotId,
  )
    ? robotId
    : onlineRobots[0] ? String(onlineRobots[0].robot_id) : ""

  async function sendMoveToPoint() {
    const target = {
      x: Number(x),
      y: Number(y),
      theta: Number(theta),
    }
    if (!selectedRobotId) {
      toast.error("Vui lòng chọn robot")
      return
    }
    if (!Object.values(target).every(Number.isFinite)) {
      toast.error("Pose đích không hợp lệ")
      return
    }
    if (
      target.x < -327.68 || target.x > 327.67
      || target.y < -327.68 || target.y > 327.67
      || target.theta < -32.768 || target.theta > 32.767
    ) {
      toast.error("Pose đích nằm ngoài phạm vi giao thức")
      return
    }

    setSending(true)
    try {
      const result = await uartApi.moveToPoint({
        robot_id: Number(selectedRobotId),
        move_id: moveId,
        ...target,
      })
      toast.success(`Robot #${result.robot_id} đã nhận lệnh di chuyển`)
      setMoveId((current) => generateMoveId(current))
      await invalidate()
    } catch (error) {
      toast.error(error instanceof Error ? error.message : "Gửi lệnh di chuyển thất bại")
    } finally {
      setSending(false)
    }
  }

  return (
    <Card>
      <CardHeader>
        <CardTitle>Di chuyển robot</CardTitle>
        <CardDescription>
          Gửi robot tới pose đích bằng MoveToPoint. Lệnh này độc lập với task
          và chỉ dùng khi vision Runtime đã dừng.
        </CardDescription>
      </CardHeader>
      <CardContent className="space-y-4">
        <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
          <div className="space-y-1.5">
            <label className="text-xs font-medium">Robot</label>
            <Select value={selectedRobotId} onValueChange={setRobotId}>
              <SelectTrigger>
                <SelectValue placeholder={
                  onlineRobots.length === 0 ? "Không có robot online" : "Chọn robot"
                } />
              </SelectTrigger>
              <SelectContent position="popper">
                {onlineRobots.map((robot) => (
                  <SelectItem
                    key={robot.robot_id}
                    value={String(robot.robot_id)}
                  >
                    <span className="flex items-center gap-2">
                      <span className="size-2 rounded-full bg-emerald-500" />
                      Robot #{robot.robot_id}
                    </span>
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
            <p className="text-xs text-muted-foreground">
              Danh sách được cập nhật từ Heartbeat; robot offline không thể chọn.
            </p>
          </div>

          <div className="space-y-1.5">
            <label className="text-xs font-medium">Move ID</label>
            <div className="flex h-9 items-center gap-2 rounded-md border bg-muted/30 px-3 text-sm">
              <Shuffle className="size-3.5 text-muted-foreground" />
              <span className="font-medium tabular-nums">#{moveId}</span>
              <Badge variant="secondary" className="ml-auto text-[10px]">Tự động</Badge>
            </div>
            <p className="text-xs text-muted-foreground">
              Tự sinh trong khoảng 0–255 và đổi sau mỗi lần gửi thành công.
            </p>
          </div>

          <div className="space-y-1.5">
            <label htmlFor="move-goal-x" className="text-xs font-medium">Goal X</label>
            <Input
              id="move-goal-x"
              type="number"
              step="any"
              min={-327.68}
              max={327.67}
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
            <label htmlFor="move-goal-y" className="text-xs font-medium">Goal Y</label>
            <Input
              id="move-goal-y"
              type="number"
              step="any"
              min={-327.68}
              max={327.67}
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
            <label htmlFor="move-goal-theta" className="text-xs font-medium">Goal Theta</label>
            <Input
              id="move-goal-theta"
              type="number"
              step="any"
              min={-32.768}
              max={32.767}
              className={NUMBER_INPUT_CLASS}
              value={theta}
              onChange={(event) => setTheta(event.target.value)}
              onWheel={(event) => event.currentTarget.blur()}
            />
            <p className="text-xs text-muted-foreground">
              Góc hướng cuối của robot, đơn vị radian.
            </p>
          </div>
        </div>
        <Button
          onClick={sendMoveToPoint}
          disabled={sending || !selectedRobotId}
        >
          <Send /> {sending ? "Đang chờ ACK..." : "Gửi lệnh di chuyển"}
        </Button>
      </CardContent>
    </Card>
  )
}


export function UartPage() {
  const { snapshot, connected } = useRobotHeartbeats()

  return (
    <div className="flex flex-col gap-6">
      <div className="grid grid-cols-1 gap-6 md:grid-cols-2">
        <UartConfigCard />
        <UartStatusCard />
      </div>
      <RobotHeartbeatCard snapshot={snapshot} connected={connected} />
      <MoveToPointCard robots={snapshot?.robots ?? []} />
    </div>
  )
}
