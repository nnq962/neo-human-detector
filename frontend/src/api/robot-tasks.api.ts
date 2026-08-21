import { apiRequest, type ApiResponse, unwrapApiResponse } from "./client"

export type RobotTaskStatus =
  | "WAITING_ROBOT"
  | "ASSIGNING"
  | "ASSIGNED"
  | "IN_PROGRESS"
  | "CANCELING"
  | "COMPLETED"
  | "FAILED"
  | "CANCELED"

export type RobotTaskPriority = "low" | "medium" | "high"
export type RobotTaskOrigin = "zone" | "manual"

export interface RobotTaskPixel {
  x: number
  y: number
}

export interface RobotTaskGoalPose {
  x: number
  y: number
  theta: number
}

export interface RobotTask {
  uid: string
  task_id: number | null
  robot_id: number | null
  camera_id: string
  camera_name: string
  zone_id: string | null
  zone_name: string | null
  origin: RobotTaskOrigin
  priority: RobotTaskPriority
  target_pixel: RobotTaskPixel | null
  goal_pose: RobotTaskGoalPose
  person_global_id: number | null
  person_similarity: number | null
  person_track_id: number | null
  status: RobotTaskStatus
  retry_count: number
  assigned_at: string
  updated_at: string
  completed_at: string | null
  last_ack_reason?: string | null
  last_ack_reason_code?: number | null
  failure_reason?: string | null
  failure_reason_code?: number | null
}

export interface CreateRobotTaskRequest {
  camera_id: string
  target_pixel: RobotTaskPixel
  priority: RobotTaskPriority
}

export interface RobotTaskMutationResult {
  uid: string
}

export interface RobotTaskSnapshot {
  sequence: number
  total: number
  active: number
  completed: number
  canceled: number
  failed: number
  tasks: RobotTask[]
}

export const robotTasksApi = {
  getSnapshot: (signal?: AbortSignal) =>
    apiRequest<ApiResponse<RobotTaskSnapshot>>("/runtime/tasks", { signal }).then(
      unwrapApiResponse,
    ),
  create: (request: CreateRobotTaskRequest) =>
    apiRequest<ApiResponse<RobotTaskMutationResult>>("/runtime/tasks", {
      method: "POST",
      body: JSON.stringify(request),
    }).then(unwrapApiResponse),
  cancel: (taskUid: string) =>
    apiRequest<ApiResponse<RobotTaskMutationResult>>(
      `/runtime/tasks/${encodeURIComponent(taskUid)}/cancel`,
      { method: "POST" },
    ).then(unwrapApiResponse),
}
