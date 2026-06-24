import { apiRequest } from "./client"

export type ReIdDevice = "auto" | "cpu" | "cuda" | "mps"

export interface ReIdEmbeddingConfig {
  batch_size: number
}

export interface ReIdTrackConfig {
  buffer_min: number
  grace_period: number
  update_interval: number
  max_buffer_size: number
  gallery_cleanup_interval: number
  max_reverify_misses: number
}

export interface ReIdQualityConfig {
  overlap_iou_threshold: number
  overlap_ioa_threshold: number
  stable_bbox_window: number
  stable_center_shift_ratio: number
  stable_size_change_ratio: number
  laplacian_var_threshold: number
}

export interface ReIdGalleryConfig {
  sim_threshold_match: number
  ema_alpha: number
  max_samples: number
  ttl_minutes: number
}

export interface ReIdConfig {
  enabled: boolean
  zone_only: boolean
  require_occupied_zone: boolean
  model_path: string | null
  device: ReIdDevice
  embedding: ReIdEmbeddingConfig
  track: ReIdTrackConfig
  quality: ReIdQualityConfig
  gallery: ReIdGalleryConfig
}

export interface ReIdConfigUpdate {
  enabled?: boolean
  zone_only?: boolean
  require_occupied_zone?: boolean
  model_path?: string
  device?: ReIdDevice
  embedding?: Partial<ReIdEmbeddingConfig>
  track?: Partial<ReIdTrackConfig>
  quality?: Partial<ReIdQualityConfig>
  gallery?: Partial<ReIdGalleryConfig>
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

export const reidApi = {
  get: () =>
    apiRequest<ApiResponse<ReIdConfig>>("/reid").then(unwrapApiResponse),

  update: (data: ReIdConfigUpdate) =>
    apiRequest<ApiResponse<ReIdConfig>>("/reid", {
      method: "PATCH",
      body: JSON.stringify(data),
    }).then(ensureApiSuccess),

  replace: (data: ReIdConfig) =>
    apiRequest<ApiResponse<ReIdConfig>>("/reid", {
      method: "PUT",
      body: JSON.stringify(data),
    }).then(ensureApiSuccess),

  delete: () =>
    apiRequest<ApiResponse<null>>("/reid", { method: "DELETE" })
      .then(ensureApiSuccess),
}
