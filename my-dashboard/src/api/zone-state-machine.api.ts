import { apiRequest } from "./client"

export interface ZoneStateMachineConfig {
  confirm_enter_time: number
  confirm_exit_time: number
  pending_enter_miss_grace_time: number
}

export type ZoneStateMachineConfigUpdate = Partial<ZoneStateMachineConfig>

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

export const zoneStateMachineApi = {
  get: () =>
    apiRequest<ApiResponse<ZoneStateMachineConfig>>("/zone-state-machine")
      .then(unwrapApiResponse),

  update: (data: ZoneStateMachineConfigUpdate) =>
    apiRequest<ApiResponse<ZoneStateMachineConfig>>("/zone-state-machine", {
      method: "PATCH",
      body: JSON.stringify(data),
    }).then(ensureApiSuccess),

  replace: (data: ZoneStateMachineConfig) =>
    apiRequest<ApiResponse<ZoneStateMachineConfig>>("/zone-state-machine", {
      method: "PUT",
      body: JSON.stringify(data),
    }).then(ensureApiSuccess),
}
