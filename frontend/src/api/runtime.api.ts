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

export interface RuntimeInferenceMetric {
  last_ms: number
  average_ms: number
  min_ms: number
  max_ms: number
  sample_count: number
}

export interface RuntimePerformanceStatus {
  yolo: RuntimeInferenceMetric | null
  reid: RuntimeInferenceMetric | null
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
  batch_size: number
  cameras: RuntimeCameraStatus[]
  performance: RuntimePerformanceStatus
  last_error: string | null
}

export interface RuntimeConfig {
  auto_start: boolean
  camera_ids: string[]
  batch_size: number
}

export interface RuntimeConfigUpdate {
  auto_start?: boolean
  camera_ids?: string[]
}

export const runtimeApi = {
  getConfig: () =>
    apiRequest<ApiResponse<RuntimeConfig>>("/runtime/config").then(unwrapApiResponse),
  updateConfig: (data: RuntimeConfigUpdate) =>
    apiRequest<ApiResponse<RuntimeConfig>>("/runtime/config", {
      method: "PATCH",
      body: JSON.stringify(data),
    }).then(unwrapApiResponse),
  start: () =>
    apiRequest<ApiResponse<RuntimeStatus>>("/runtime/start", { method: "POST" }).then(unwrapApiResponse),
  stop: () =>
    apiRequest<ApiResponse<RuntimeStatus>>("/runtime/stop", { method: "POST" }).then(unwrapApiResponse),
  restart: () =>
    apiRequest<ApiResponse<RuntimeStatus>>("/runtime/restart", { method: "POST" }).then(unwrapApiResponse),
}
