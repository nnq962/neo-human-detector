import {
  CircleCheck,
  CirclePlus,
  LoaderCircle,
  MapPin,
  Trash2,
  X,
} from "lucide-react"

import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import {
  Popover,
  PopoverContent,
  PopoverTrigger,
} from "@/components/ui/popover"
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select"
import {
  PRIORITY_ENTRIES,
  PRIORITY_VIEW,
  STATUS_VIEW,
} from "@/components/navigation/navigation-task-view"
import { PriorityIcon } from "@/components/navigation/priority-icon"
import type {
  NavigationTask,
  NavigationTaskPriority,
} from "@/lib/navigation-tasks"
import { cn } from "@/lib/utils"

interface NavigationTaskMarkerProps {
  task: NavigationTask
  cameraName: string
  open: boolean
  submitting: boolean
  canceling: boolean
  onOpenChange: (open: boolean) => void
  onPriorityChange: (priority: NavigationTaskPriority) => void
  onCancel: () => void
  onSubmit: () => void
}

export function NavigationTaskMarker({
  task,
  cameraName,
  open,
  submitting,
  canceling,
  onOpenChange,
  onPriorityChange,
  onCancel,
  onSubmit,
}: NavigationTaskMarkerProps) {
  const isDraft = task.kind === "draft"
  const isCanceling = canceling || task.status === "canceling"
  const visibleStatus = submitting ? "submitting" : isCanceling ? "canceling" : task.status
  const cancelDisabled = submitting
    || isCanceling
    || (!isDraft && ["done", "error", "canceling"].includes(task.status))

  return (
    <Popover open={open} onOpenChange={onOpenChange}>
      <PopoverTrigger asChild>
        <button
          type="button"
          data-navigation-task-trigger
          aria-label={`Xem task ${task.displayId}`}
          className={cn(
            "absolute z-40 grid size-7 -translate-x-1/2 -translate-y-full place-items-center drop-shadow-md transition-opacity duration-1000 focus-visible:outline-none",
            task.isFading && "pointer-events-none opacity-0",
          )}
          style={{ left: `${task.x}%`, top: `${task.y}%` }}
          onClick={(event) => event.stopPropagation()}
        >
          <MapPin
            className={cn("size-7 text-white", STATUS_VIEW[visibleStatus].pinClassName)}
            strokeWidth={1.75}
          />
          <span
            className={cn(
              "absolute -top-1 -right-1 grid size-3.5 place-items-center rounded-full text-white ring-1 ring-white",
              PRIORITY_VIEW[task.priority].dotClassName,
            )}
          >
            <PriorityIcon priority={task.priority} className="size-2.5" />
          </span>
        </button>
      </PopoverTrigger>
      <PopoverContent
        className="w-60 gap-0 overflow-hidden p-0"
        side="top"
        sideOffset={8}
        onClick={(event) => event.stopPropagation()}
        onCloseAutoFocus={(event) => event.preventDefault()}
        onPointerDownOutside={(event) => {
          const target = event.target
          if (
            target instanceof Element
            && target.closest("[data-navigation-task-trigger]")
          ) {
            event.preventDefault()
          }
        }}
      >
        <div className="flex items-center justify-between border-b px-3 py-2">
          <div className="flex items-center gap-2">
            {isDraft ? <MapPin className="size-4" /> : <CircleCheck className="size-4" />}
            <span className="text-sm font-semibold">
              {isDraft ? "Task nháp" : `Task #${task.displayId}`}
            </span>
          </div>
          <button
            type="button"
            className="rounded-sm text-muted-foreground hover:text-foreground"
            onClick={() => onOpenChange(false)}
            aria-label="Đóng chi tiết task"
          >
            <X className="size-4" />
          </button>
        </div>
        <div className="space-y-2 p-3 text-xs">
          <div className="flex items-center justify-between gap-3">
            <span className="text-muted-foreground">Trạng thái</span>
            <Badge
              variant="outline"
              className={STATUS_VIEW[visibleStatus].badgeClassName}
            >
              {STATUS_VIEW[visibleStatus].label}
            </Badge>
          </div>
          <div className="flex items-center justify-between gap-3">
            <span className="text-muted-foreground">Camera</span>
            <span className="truncate font-medium">{cameraName}</span>
          </div>
          {!isDraft ? (
            <div className="flex items-center justify-between gap-3">
              <span className="text-muted-foreground">Nguồn</span>
              <Badge variant="secondary">
                {task.origin === "zone" ? `Zone: ${task.zoneName}` : "Task thủ công"}
              </Badge>
            </div>
          ) : null}
          <div className="flex items-center justify-between gap-3">
            <span className="text-muted-foreground">Ưu tiên</span>
            <Select
              value={task.priority}
              disabled={!isDraft || submitting}
              onValueChange={(value) => onPriorityChange(value as NavigationTaskPriority)}
            >
              <SelectTrigger size="sm" className="min-w-28">
                <SelectValue />
              </SelectTrigger>
              <SelectContent position="popper" align="center">
                {PRIORITY_ENTRIES.map(([priority, view]) => (
                  <SelectItem key={priority} value={priority}>
                    <span className={cn("size-2 rounded-full", view.dotClassName)} />
                    {view.label}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>
          <div className="flex items-center justify-between gap-3">
            <span className="text-muted-foreground">Tọa độ ảnh</span>
            <span>{task.pixelX} × {task.pixelY} px</span>
          </div>
          <div className="flex items-center justify-between gap-3">
            <span className="text-muted-foreground">Khởi tạo</span>
            <span>{task.createdAt.toLocaleTimeString("vi-VN")}</span>
          </div>
          {task.status === "error" && task.failureReason ? (
            <div className="flex items-start justify-between gap-3">
              <span className="shrink-0 text-muted-foreground">Lý do lỗi</span>
              <span className="break-words text-right font-medium text-destructive">
                {task.failureReason}
              </span>
            </div>
          ) : task.lastAckReason ? (
            <div className="flex items-start justify-between gap-3">
              <span className="shrink-0 text-muted-foreground">ACK gần nhất</span>
              <span className="break-words text-right font-medium">
                {task.lastAckReason}
              </span>
            </div>
          ) : null}
          <div className="mt-1 grid grid-cols-2 gap-2">
            <Button
              type="button"
              variant="destructive"
              size="sm"
              disabled={cancelDisabled}
              onClick={onCancel}
            >
              {isCanceling
                ? <LoaderCircle className="animate-spin" />
                : <Trash2 />}
              {isDraft ? "Xóa draft" : isCanceling ? "Đang hủy" : "Hủy task"}
            </Button>
            <Button
              type="button"
              size="sm"
              disabled={!isDraft || submitting}
              onClick={onSubmit}
            >
              {submitting
                ? <LoaderCircle className="animate-spin" />
                : isDraft ? <CirclePlus /> : <CircleCheck />}
              {submitting ? "Đang thêm" : isDraft ? "Thêm task" : "Đã thêm"}
            </Button>
          </div>
        </div>
      </PopoverContent>
    </Popover>
  )
}
