import { apiRequest } from "./client"

// ── Types ────────────────────────────────────────────────────────────────────

export interface GoalPose {
  x: number
  y: number
  theta: number
}

export interface Zone {
  id?: string
  name: string
  goal_pose?: GoalPose | null
  points: [number, number][]
}

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

export interface ApiResponse<T> {
  success: boolean
  message: string
  data: T
}

function ensureApiSuccess<T>(response: ApiResponse<T>): ApiResponse<T> {
  if (!response.success) {
    throw new Error(response.message || "API request failed")
  }

  return response
}

function unwrapApiResponse<T>(response: ApiResponse<T>): T {
  return ensureApiSuccess(response).data
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
