import { apiRequest, type ApiResponse, ensureApiSuccess, unwrapApiResponse } from "./client"

export interface RobotDispatchConfig {
  enabled: boolean
  use_reid: boolean
  ack_timeout_seconds: number
  max_retries: number
}

export type RobotDispatchConfigUpdate = Partial<RobotDispatchConfig>

export const robotDispatchApi = {
  get: () =>
    apiRequest<ApiResponse<RobotDispatchConfig>>("/robot-dispatch")
      .then(unwrapApiResponse),

  update: (data: RobotDispatchConfigUpdate) =>
    apiRequest<ApiResponse<RobotDispatchConfig>>("/robot-dispatch", {
      method: "PATCH",
      body: JSON.stringify(data),
    }).then(ensureApiSuccess),
}
