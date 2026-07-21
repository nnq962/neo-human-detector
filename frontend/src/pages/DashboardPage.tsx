import { memo, useState } from "react"
import {
  Activity,
  Ban,
  Bot,
  CheckCircle2,
  CircleAlert,
  Clock3,
  MapPin,
  Send,
  User,
  XCircle,
} from "lucide-react"
import { Link } from "react-router-dom"
import { Badge } from "@/components/ui/badge"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { Skeleton } from "@/components/ui/skeleton"
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select"
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table"
import { CameraPreview } from "@/components/camera-preview"
import type {
  RobotTask,
  RobotTaskStatus,
} from "@/api/robot-tasks.api"
import { useCameras, type Camera } from "@/hooks/use-cameras"
import { useRobotTasks } from "@/hooks/use-robot-tasks"
import { cn } from "@/lib/utils"

type TaskFilter = "all" | "active" | "completed" | "attention"

const TASK_STATUS_VIEW = {
  WAITING_ROBOT: {
    label: "Chờ robot",
    icon: Clock3,
    className: "border-slate-500/30 bg-slate-500/10 text-slate-700 dark:text-slate-400",
  },
  ASSIGNING: {
    label: "Đang assign",
    icon: Send,
    className: "border-amber-500/30 bg-amber-500/10 text-amber-700 dark:text-amber-400",
  },
  ASSIGNED: {
    label: "Đã assign",
    icon: Send,
    className: "border-cyan-500/30 bg-cyan-500/10 text-cyan-700 dark:text-cyan-400",
  },
  IN_PROGRESS: {
    label: "Đang thực hiện",
    icon: Activity,
    className: "border-blue-500/30 bg-blue-500/10 text-blue-700 dark:text-blue-400",
  },
  CANCELING: {
    label: "Đang hủy",
    icon: Ban,
    className: "border-orange-500/30 bg-orange-500/10 text-orange-700 dark:text-orange-400",
  },
  COMPLETED: {
    label: "Hoàn thành",
    icon: CheckCircle2,
    className: "border-emerald-500/30 bg-emerald-500/10 text-emerald-700 dark:text-emerald-400",
  },
  FAILED: {
    label: "Thất bại",
    icon: CircleAlert,
    className: "border-red-500/30 bg-red-500/10 text-red-700 dark:text-red-400",
  },
  CANCELED: {
    label: "Đã hủy",
    icon: XCircle,
    className: "border-zinc-500/30 bg-zinc-500/10 text-zinc-600 dark:text-zinc-400",
  },
} satisfies Record<
  RobotTaskStatus,
  { label: string; icon: typeof Activity; className: string }
>

// ── Camera cell ───────────────────────────────────────────────────────────────

const CameraCell = memo(function CameraCell({ camera }: { camera: Camera }) {
  return (
    <Link
      to={`/cameras/${camera.id}`}
      className="relative block aspect-video overflow-hidden rounded-lg ring-1 ring-border transition-shadow hover:ring-2 hover:ring-ring"
    >
      <CameraPreview
        src={camera.webrtc_address ?? ""}
        zones={camera.zones}
        bboxCameraId={camera.id}
        hideFaceKeypoints={true}
      />
      <div className="pointer-events-none absolute bottom-3 left-3 z-30 rounded-md bg-black/60 px-2.5 py-1 text-xs font-medium text-white backdrop-blur-sm">
        {camera.name}
      </div>
    </Link>
  )
})

function TaskStatusBadge({ status }: { status: RobotTaskStatus }) {
  const view = TASK_STATUS_VIEW[status]
  const Icon = view.icon

  return (
    <Badge variant="outline" className={cn("gap-1.5", view.className)}>
      <Icon />
      {view.label}
    </Badge>
  )
}

function TaskIdentity({ task }: { task: RobotTask }) {
  if (task.person_global_id === null) {
    return <span className="text-xs text-muted-foreground">Zone-only</span>
  }

  return (
    <div>
      <p className="flex items-center gap-1.5 text-sm font-medium">
        <User className="size-3.5 text-muted-foreground" />
        ID {task.person_global_id}
      </p>
      <Badge variant="secondary" className="mt-1 font-normal">
        {Math.round((task.person_similarity ?? 0) * 100)}%
      </Badge>
    </div>
  )
}

function TaskGoal({ task }: { task: RobotTask }) {
  return (
    <div>
      <div className="flex items-center gap-1.5">
        <MapPin className="size-3.5 shrink-0 text-muted-foreground" />
        <p className="text-sm font-medium">{task.zone_name}</p>
      </div>
      <div className="mt-1 flex flex-wrap gap-1">
        <Badge variant="secondary" className="font-normal">
          {task.goal_pose.x.toFixed(2)}
        </Badge>
        <Badge variant="secondary" className="font-normal">
          {task.goal_pose.y.toFixed(2)}
        </Badge>
        <Badge variant="secondary" className="font-normal">
          {task.goal_pose.theta.toFixed(2)}
        </Badge>
      </div>
    </div>
  )
}

function formatTaskTime(value: string) {
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return "—"
  return date.toLocaleTimeString("vi-VN", { hour12: false })
}

function formatTaskAge(value: string) {
  const timestamp = new Date(value).getTime()
  if (Number.isNaN(timestamp)) return "—"
  const seconds = Math.max(0, Math.floor((Date.now() - timestamp) / 1000))
  if (seconds < 5) return "Vừa xong"
  if (seconds < 60) return `${seconds} giây trước`
  const minutes = Math.floor(seconds / 60)
  if (minutes < 60) return `${minutes} phút trước`
  const hours = Math.floor(minutes / 60)
  return `${hours} giờ trước`
}

function RobotTasksCard() {
  const [filter, setFilter] = useState<TaskFilter>("all")
  const { snapshot, connected } = useRobotTasks()
  const tasks = snapshot?.tasks ?? []

  const activeCount = snapshot?.active ?? 0
  const completedCount = snapshot?.completed ?? 0
  const canceledCount = snapshot?.canceled ?? 0
  const failedCount = snapshot?.failed ?? 0

  const visibleTasks = tasks.filter((task) => {
    if (filter === "active") {
      return [
        "WAITING_ROBOT",
        "ASSIGNING",
        "ASSIGNED",
        "IN_PROGRESS",
        "CANCELING",
      ].includes(task.status)
    }
    if (filter === "completed") {
      return task.status === "COMPLETED" || task.status === "CANCELED"
    }
    if (filter === "attention") {
      return task.status === "FAILED" || task.status === "CANCELING"
    }
    return true
  })

  const summaries = [
    {
      label: "Đang xử lý",
      value: activeCount,
      icon: Activity,
      iconClassName: "text-blue-500",
    },
    {
      label: "Hoàn thành",
      value: completedCount,
      icon: CheckCircle2,
      iconClassName: "text-emerald-500",
    },
    {
      label: "Đã hủy",
      value: canceledCount,
      icon: Ban,
      iconClassName: "text-zinc-500",
    },
    {
      label: "Thất bại",
      value: failedCount,
      icon: CircleAlert,
      iconClassName: "text-red-500",
    },
  ]

  return (
    <Card>
      <CardHeader>
        <div className="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
          <div className="space-y-1">
            <div className="flex items-center gap-2">
              <CardTitle>Robot tasks</CardTitle>
              <Badge
                variant={connected ? "secondary" : "outline"}
                className="gap-1.5"
              >
                <span
                  className={cn(
                    "size-1.5 rounded-full",
                    connected ? "bg-emerald-500" : "bg-amber-500",
                  )}
                />
                {connected ? "Realtime" : snapshot ? "Snapshot" : "Đang tải"}
              </Badge>
            </div>
            <p className="text-sm text-muted-foreground">
              Theo dõi task assign, trạng thái thực thi và yêu cầu hủy.
            </p>
          </div>
          <div className="flex w-full sm:w-auto">
            <Select
              value={filter}
              onValueChange={(value) => setFilter(value as TaskFilter)}
            >
              <SelectTrigger className="min-w-0 flex-1 sm:w-40 sm:flex-none">
                <SelectValue />
              </SelectTrigger>
              <SelectContent position="popper">
                <SelectItem value="all">Tất cả task</SelectItem>
                <SelectItem value="active">Đang xử lý</SelectItem>
                <SelectItem value="completed">Đã kết thúc</SelectItem>
                <SelectItem value="attention">Cần chú ý</SelectItem>
              </SelectContent>
            </Select>
          </div>
        </div>
      </CardHeader>

      <CardContent className="space-y-5">
        <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
          {summaries.map((summary) => {
            const Icon = summary.icon
            return (
              <div
                key={summary.label}
                className="flex min-w-0 items-center gap-3 rounded-lg border bg-muted/20 p-3"
              >
                <div className="grid size-9 shrink-0 place-items-center rounded-md bg-background ring-1 ring-border">
                  <Icon className={cn("size-4", summary.iconClassName)} />
                </div>
                <div className="min-w-0">
                  <p className="truncate text-xs text-muted-foreground">
                    {summary.label}
                  </p>
                  <p className="text-xl font-semibold leading-tight">
                    {summary.value}
                  </p>
                </div>
              </div>
            )
          })}
        </div>

        {!snapshot ? (
          <Skeleton className="h-40 rounded-lg" />
        ) : (
          <>
        <div className="hidden overflow-hidden rounded-lg border lg:block">
          <Table className="table-fixed">
            <TableHeader className="bg-muted/40">
              <TableRow>
                <TableHead className="w-[13%]">Task</TableHead>
                <TableHead className="w-[18%]">Robot</TableHead>
                <TableHead className="w-[20%]">Điểm đến</TableHead>
                <TableHead className="w-[14%]">Người</TableHead>
                <TableHead className="w-[19%]">Trạng thái</TableHead>
                <TableHead className="w-[16%]">Cập nhật</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {visibleTasks.map((task) => (
                <TableRow key={task.uid}>
                  <TableCell className="overflow-hidden">
                    <p className="font-medium">
                      {task.task_id === null ? "Chưa cấp ID" : `#${task.task_id}`}
                    </p>
                    <p className="text-xs text-muted-foreground">
                      {formatTaskTime(task.assigned_at)}
                    </p>
                  </TableCell>
                  <TableCell className="overflow-hidden">
                    <div className="flex min-w-0 items-center gap-2">
                      <div className="grid size-7 place-items-center rounded-full bg-primary/10 text-primary">
                        <Bot className="size-3.5" />
                      </div>
                      <span className="truncate font-medium">
                        {task.robot_id === null
                          ? "Đang chờ robot"
                          : `Robot #${task.robot_id}`}
                      </span>
                    </div>
                  </TableCell>
                  <TableCell className="overflow-hidden">
                    <TaskGoal task={task} />
                  </TableCell>
                  <TableCell className="overflow-hidden">
                    <TaskIdentity task={task} />
                  </TableCell>
                  <TableCell className="overflow-hidden">
                    <div className="flex flex-col items-start gap-1.5">
                      <TaskStatusBadge status={task.status} />
                      {task.retry_count > 0 && (
                        <p className="text-[11px] text-muted-foreground">
                          Retry {task.retry_count} lần
                        </p>
                      )}
                    </div>
                  </TableCell>
                  <TableCell className="overflow-hidden">
                    <div className="flex items-center gap-1.5 whitespace-nowrap text-xs tabular-nums text-muted-foreground">
                      <Clock3 className="size-3.5 shrink-0" />
                      {formatTaskAge(task.updated_at)}
                    </div>
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </div>

        <div className="grid gap-3 lg:hidden">
          {visibleTasks.map((task) => (
            <div key={task.uid} className="rounded-lg border p-3">
              <div className="flex items-start justify-between gap-3">
                <div className="flex min-w-0 items-center gap-2.5">
                  <div className="grid size-9 shrink-0 place-items-center rounded-full bg-primary/10 text-primary">
                    <Bot className="size-4" />
                  </div>
                  <div className="min-w-0">
                    <p className="truncate text-sm font-medium">
                      {task.task_id === null
                        ? "Task chưa cấp ID"
                        : `Task #${task.task_id}`}
                      {task.robot_id === null
                        ? " · Chờ robot"
                        : ` · Robot #${task.robot_id}`}
                    </p>
                    <p className="text-xs text-muted-foreground">
                      Assign lúc {formatTaskTime(task.assigned_at)}
                    </p>
                  </div>
                </div>
                <TaskStatusBadge status={task.status} />
              </div>

              <div className="my-3 border-t" />

              <div className="grid gap-3 sm:grid-cols-2">
                <TaskGoal task={task} />
                <div className="flex items-start justify-between gap-3 sm:block">
                  <TaskIdentity task={task} />
                  <div className="flex items-center gap-1.5 text-xs text-muted-foreground sm:mt-1">
                    <Clock3 className="size-3.5" />
                    {formatTaskAge(task.updated_at)}
                  </div>
                </div>
              </div>

            </div>
          ))}
        </div>

        {visibleTasks.length === 0 && (
          <div className="rounded-lg border border-dashed py-10 text-center">
            <p className="text-sm font-medium">Không có task phù hợp</p>
            <p className="mt-1 text-xs text-muted-foreground">
              {tasks.length === 0
                ? "Chưa có task nào trong phiên runtime này."
                : "Thử chọn một bộ lọc khác."}
            </p>
          </div>
        )}
          </>
        )}
      </CardContent>
    </Card>
  )
}

// ── Page ──────────────────────────────────────────────────────────────────────

export function DashboardPage() {
  const { data: cameras = [], isLoading: camerasLoading } = useCameras()
  const gridCols = cameras.length <= 1 ? "grid-cols-1" : "grid-cols-1 sm:grid-cols-2"

  return (
    <div className="flex flex-col gap-6">

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

      <RobotTasksCard />

    </div>
  )
}
