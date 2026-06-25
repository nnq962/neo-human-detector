import { apiRequest, type ApiResponse, unwrapApiResponse } from "./client"

export type RuntimeState = "stopped" | "starting" | "running" | "stopping" | "error"

export interface RuntimeCameraStatus {
  id: string
  name: string
  source: string
  zones: number
  fps: number | null
  zone_states: Record<string, string>
}

export interface RuntimeStatus {
  state: RuntimeState
  is_running: boolean
  thread_alive: boolean
  config_path: string | null
  preview: boolean | null
  started_at: string | null
  stopped_at: string | null
  uptime_seconds: number | null
  cameras: RuntimeCameraStatus[]
  last_error: string | null
}

export const runtimeApi = {
  start: () =>
    apiRequest<ApiResponse<RuntimeStatus>>("/runtime/start", { method: "POST" }).then(unwrapApiResponse),
  stop: () =>
    apiRequest<ApiResponse<RuntimeStatus>>("/runtime/stop", { method: "POST" }).then(unwrapApiResponse),
  restart: () =>
    apiRequest<ApiResponse<RuntimeStatus>>("/runtime/restart", { method: "POST" }).then(unwrapApiResponse),
}
