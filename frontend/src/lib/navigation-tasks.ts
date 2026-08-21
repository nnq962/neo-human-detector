import type { Camera } from "@/api/cameras.api"
import type { RobotTask, RobotTaskStatus } from "@/api/robot-tasks.api"
import type { VideoSize } from "@/components/camera-preview/types"

export const TASK_COMPLETION_FADE_DELAY_MS = 10_000
export const TASK_COMPLETION_REMOVE_DELAY_MS = 11_000

export type NavigationTaskStatus =
  | "draft"
  | "submitting"
  | "pending"
  | "active"
  | "canceling"
  | "done"
  | "error"

export type NavigationTaskPriority = RobotTask["priority"]

export interface NavigationTask {
  id: string
  displayId: string
  kind: "draft" | "runtime"
  origin: RobotTask["origin"] | null
  zoneName: string | null
  x: number
  y: number
  pixelX: number
  pixelY: number
  createdAt: Date
  completedAt: Date | null
  isFading: boolean
  priority: RobotTask["priority"]
  status: NavigationTaskStatus
  lastAckReason?: string | null
  failureReason?: string | null
}

export function mapRuntimeTaskStatus(
  status: RobotTaskStatus,
): NavigationTaskStatus | null {
  if (status === "CANCELED") return null
  if (status === "WAITING_ROBOT" || status === "ASSIGNING") return "pending"
  if (status === "ASSIGNED" || status === "IN_PROGRESS") return "active"
  if (status === "CANCELING") return "canceling"
  if (status === "COMPLETED") return "done"
  return "error"
}

export function mapRuntimeTaskToNavigation(
  task: RobotTask,
  camera: Camera,
  videoSize: VideoSize | null,
  clockMs: number,
): NavigationTask | null {
  const status = mapRuntimeTaskStatus(task.status)
  if (!status) return null

  const zone = camera.zones.find((candidate) => (
    candidate.id === task.zone_id || candidate.name === task.zone_name
  ))
  const targetPixel = task.target_pixel ?? (
    zone?.service_point
      ? { x: zone.service_point[0], y: zone.service_point[1] }
      : null
  )
  if (!targetPixel) return null

  const completedAt = task.completed_at ? new Date(task.completed_at) : null
  const completedTimestamp = completedAt?.getTime()
  const completedAge = clockMs > 0 && completedTimestamp !== undefined
    && Number.isFinite(completedTimestamp)
    ? clockMs - completedTimestamp
    : 0
  if (
    status === "done"
    && completedAge >= TASK_COMPLETION_REMOVE_DELAY_MS
  ) return null

  const width = videoSize?.width ?? 1920
  const height = videoSize?.height ?? 1080
  return {
    id: task.uid,
    displayId: task.task_id === null ? task.uid.slice(-6) : String(task.task_id),
    kind: "runtime",
    origin: task.origin,
    zoneName: task.zone_name,
    x: Math.min(100, Math.max(0, (targetPixel.x / width) * 100)),
    y: Math.min(100, Math.max(0, (targetPixel.y / height) * 100)),
    pixelX: targetPixel.x,
    pixelY: targetPixel.y,
    createdAt: new Date(task.assigned_at),
    completedAt,
    isFading: status === "done"
      && completedAge >= TASK_COMPLETION_FADE_DELAY_MS,
    priority: task.priority,
    status,
    lastAckReason: task.last_ack_reason ?? null,
    failureReason: task.failure_reason ?? null,
  }
}
