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
  zone_id: string
  zone_name: string
  goal_pose: RobotTaskGoalPose
  person_global_id: number | null
  person_similarity: number | null
  person_track_id: number | null
  status: RobotTaskStatus
  retry_count: number
  assigned_at: string
  updated_at: string
  completed_at: string | null
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
  getSnapshot: () =>
    apiRequest<ApiResponse<RobotTaskSnapshot>>("/runtime/tasks").then(
      unwrapApiResponse,
    ),
}
