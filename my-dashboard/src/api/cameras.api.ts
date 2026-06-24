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

// ── API calls ────────────────────────────────────────────────────────────────

export const camerasApi = {
  list: () =>
    apiRequest<Camera[]>("/cameras"),

  get: (id: string) =>
    apiRequest<Camera>(`/cameras/${id}`),

  create: (data: CameraCreate) =>
    apiRequest<Camera>("/cameras", {
      method: "POST",
      body: JSON.stringify(data),
    }),

  replace: (id: string, data: CameraCreate) =>
    apiRequest<Camera>(`/cameras/${id}`, {
      method: "PUT",
      body: JSON.stringify(data),
    }),

  update: (id: string, data: CameraUpdate) =>
    apiRequest<Camera>(`/cameras/${id}`, {
      method: "PATCH",
      body: JSON.stringify(data),
    }),

  delete: (id: string) =>
    apiRequest<void>(`/cameras/${id}`, { method: "DELETE" }),
}
