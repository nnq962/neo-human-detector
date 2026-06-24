import { apiRequest } from "./client"

export type DetectionTask = "detect" | "pose"
export type DetectionModelSize = "nano" | "medium"
export type DetectionBatchSize = 1 | 2

export interface DetectionConfig {
  task: DetectionTask
  model_size: DetectionModelSize
  batch_size: DetectionBatchSize
  conf: number
  verbose: boolean
}

export type DetectionConfigUpdate = Partial<DetectionConfig>

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
