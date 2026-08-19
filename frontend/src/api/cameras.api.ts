import { apiRequest, type ApiResponse, ensureApiSuccess, unwrapApiResponse } from "./client"

// ── Types ────────────────────────────────────────────────────────────────────

export interface Zone {
  id?: string
  name: string
  priority: ZonePriority
  service_point?: [number, number] | null
  points: [number, number][]
}

export type ZonePriority = "low" | "medium" | "high"

export interface StreamConfig {
  source: string
  protocol: string
  on_demand: boolean
}

export interface Camera {
  id: string
  name: string
  enabled: boolean
  stream: StreamConfig
  zones: Zone[]
  webrtc_address?: string | null
}

export interface CameraCreate {
  name: string
  stream: StreamConfig
  enabled?: boolean
  zones?: Zone[]
}

export interface StreamConfigUpdate {
  source?: string
  protocol?: string
  on_demand?: boolean
}

export interface CameraUpdate {
  name?: string
  enabled?: boolean
  stream?: StreamConfigUpdate
  zones?: Zone[]
}

// ── API calls ────────────────────────────────────────────────────────────────

export const camerasApi = {
  list: () =>
    apiRequest<ApiResponse<Camera[]>>("/cameras").then(unwrapApiResponse),

  get: (id: string) =>
    apiRequest<ApiResponse<Camera>>(`/cameras/${id}`).then(unwrapApiResponse),

  create: (data: CameraCreate) =>
    apiRequest<ApiResponse<Camera>>("/cameras", {
      method: "POST",
      body: JSON.stringify(data),
    }).then(ensureApiSuccess),

  replace: (id: string, data: CameraCreate) =>
    apiRequest<ApiResponse<Camera>>(`/cameras/${id}`, {
      method: "PUT",
      body: JSON.stringify(data),
    }).then(ensureApiSuccess),

  update: (id: string, data: CameraUpdate) =>
    apiRequest<ApiResponse<Camera>>(`/cameras/${id}`, {
      method: "PATCH",
      body: JSON.stringify(data),
    }).then(ensureApiSuccess),

  delete: (id: string) =>
    apiRequest<ApiResponse<Camera>>(`/cameras/${id}`, { method: "DELETE" })
      .then(ensureApiSuccess),
}
