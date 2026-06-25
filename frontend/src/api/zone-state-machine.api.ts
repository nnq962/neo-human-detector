import { apiRequest, type ApiResponse, ensureApiSuccess, unwrapApiResponse } from "./client"

export interface ZoneStateMachineConfig {
  confirm_enter_time: number
  confirm_exit_time: number
  pending_enter_miss_grace_time: number
}

export type ZoneStateMachineConfigUpdate = Partial<ZoneStateMachineConfig>

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
