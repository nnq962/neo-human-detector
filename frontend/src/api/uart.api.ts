import { apiRequest, type ApiResponse, ensureApiSuccess, unwrapApiResponse } from "./client"

export interface UartConfig {
  port: string
  baudrate: number
}

export interface UartConfigUpdate {
  port?: string
  baudrate?: number
}

export interface ManualRobotTask {
  robot_id: number
  task_id: number
  state: string
  created_at: number
  updated_at: number
  x?: number | null
  y?: number | null
  theta?: number | null
}

export interface UartStatus {
  protocol: "v2"
  port: string
  baudrate: number
  timeout: number
  connected: boolean
  listening: boolean
  last_connected_at: number | null
  last_disconnected_at: number | null
  last_received_at: number | null
  last_error: string | null
  manual_tasks: ManualRobotTask[]
}

export type RobotState = "IDLE" | "SERVING" | "ERROR" | "UNKNOWN"

export interface RobotHeartbeat {
  robot_id: number
  state: RobotState
  state_code: number
  online: boolean
  heartbeat_timestamp: number
  heartbeat_age_seconds: number
  x: number
  y: number
  theta: number
}

export interface RobotHeartbeatSnapshot {
  total: number
  online: number
  latest_heartbeat_age_seconds: number | null
  robots: RobotHeartbeat[]
}

export interface UartAckResult {
  result_code: number
  result: string
  reason_code: number
  reason: string
}

export interface MoveToPointRequest {
  robot_id: number
  x: number
  y: number
  theta: number
}

export interface MoveToPointResult {
  message_type: "move_to_point"
  robot_id: number
  move_id: number
  acknowledged: boolean
  ack: UartAckResult
  target: {
    x: number
    y: number
    theta: number
  }
}

export type UartMessageRequest =
  | {
      message_type: "task_assign"
      robot_id: number
      task_id: number
      x: number
      y: number
      theta: number
    }
  | {
      message_type: "task_cancel"
      robot_id: number
      task_id: number
    }

export interface UartMessageResult {
  message_type: UartMessageRequest["message_type"]
  robot_id: number
  task_id: number
  acknowledged: boolean
  ack: UartAckResult
  task: ManualRobotTask
}

export const uartApi = {
  get: () => apiRequest<ApiResponse<UartConfig>>("/uart").then(unwrapApiResponse),
  getStatus: () =>
    apiRequest<ApiResponse<UartStatus>>("/uart/status").then(unwrapApiResponse),
  getRobots: () =>
    apiRequest<ApiResponse<RobotHeartbeatSnapshot>>("/uart/robots").then(unwrapApiResponse),
  update: (data: UartConfigUpdate) =>
    apiRequest<ApiResponse<UartConfig>>("/uart", {
      method: "PATCH",
      body: JSON.stringify(data),
    }).then(ensureApiSuccess),
  sendMessage: (message: UartMessageRequest) =>
    apiRequest<ApiResponse<UartMessageResult>>("/uart/messages", {
      method: "POST",
      body: JSON.stringify(message),
    }).then(unwrapApiResponse),
  moveToPoint: (request: MoveToPointRequest) =>
    apiRequest<ApiResponse<MoveToPointResult>>("/uart/move-to-point", {
      method: "POST",
      body: JSON.stringify(request),
    }).then(unwrapApiResponse),
}
