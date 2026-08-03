import { apiRequest, type ApiResponse, ensureApiSuccess, unwrapApiResponse } from "./client"

export interface DetectionConfig {
  model_id: string | null
  conf: number
  verbose: boolean
}

export type DetectionConfigUpdate = Partial<DetectionConfig>

export const detectionApi = {
  get: () =>
    apiRequest<ApiResponse<DetectionConfig>>("/detection")
      .then(unwrapApiResponse),

  update: (data: DetectionConfigUpdate) =>
    apiRequest<ApiResponse<DetectionConfig>>("/detection", {
      method: "PATCH",
      body: JSON.stringify(data),
    }).then(ensureApiSuccess),

  replace: (data: DetectionConfig) =>
    apiRequest<ApiResponse<DetectionConfig>>("/detection", {
      method: "PUT",
      body: JSON.stringify(data),
    }).then(ensureApiSuccess),

  delete: () =>
    apiRequest<ApiResponse<DetectionConfig>>("/detection", { method: "DELETE" })
      .then(ensureApiSuccess),
}
