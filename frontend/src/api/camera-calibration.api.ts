import { apiRequest, type ApiResponse, unwrapApiResponse } from "./client"

export type CalibrationQualityRating =
  | "GOOD"
  | "CHECK"
  | "RECALIBRATE"
  | "LIMITED"

export interface CalibrationPointInput {
  id: string
  pixel: { u: number; v: number }
  world: { x: number; y: number }
  robot_id: number | null
}

export interface CalibrationPreviewRequest {
  image_size: { width: number; height: number }
  points: CalibrationPointInput[]
  ransac_threshold_m?: number
}

export interface CalibrationApplyRequest extends CalibrationPreviewRequest {
  accept_warning?: boolean
}

export interface CalibrationPointResult {
  id: string
  valid: boolean
  predicted_world: { x: number; y: number }
  error_m: number
  validation_error_m: number | null
}

export interface CalibrationPreviewResult {
  camera_id: string
  image_size: { width: number; height: number }
  direction: "pixel_to_world"
  method: "ransac"
  ransac_threshold_m: number
  homography: number[][]
  quality: {
    valid_points: number
    total_points: number
    valid_ratio: number
    rmse_inlier_m: number
    rmse_all_m: number
    validation_rmse_m: number | null
    rating: CalibrationQualityRating
  }
  points: CalibrationPointResult[]
}

export interface CameraCalibration {
  camera_id: string
  image_size: { width: number; height: number }
  direction: "pixel_to_world"
  method: "ransac"
  ransac_threshold_m: number
  homography: number[][]
  quality: CalibrationPreviewResult["quality"]
  points: Array<{
    id: string
    pixel: [number, number]
    world: [number, number]
    robot_id: number | null
    valid: boolean
    predicted_world: [number, number]
    error_m: number
    validation_error_m?: number | null
  }>
  updated_at: string
}

export function cameraCalibrationQueryKey(
  cameraId: string | null,
  publicAccess = false,
) {
  return [
    "camera-calibration",
    publicAccess ? "public" : "private",
    cameraId,
  ] as const
}

export const cameraCalibrationApi = {
  get: (cameraId: string, signal?: AbortSignal) =>
    apiRequest<ApiResponse<CameraCalibration | null>>(
      `/cameras/${cameraId}/calibration`,
      { signal },
    ).then(unwrapApiResponse),

  getPublic: (cameraId: string) =>
    apiRequest<ApiResponse<CameraCalibration | null>>(
      `/public/cameras/${cameraId}/calibration`,
    ).then(unwrapApiResponse),

  preview: (cameraId: string, request: CalibrationPreviewRequest) =>
    apiRequest<ApiResponse<CalibrationPreviewResult>>(
      `/cameras/${cameraId}/calibration/preview`,
      {
        method: "POST",
        body: JSON.stringify(request),
      },
    ).then(unwrapApiResponse),

  apply: (cameraId: string, request: CalibrationApplyRequest) =>
    apiRequest<ApiResponse<CameraCalibration>>(
      `/cameras/${cameraId}/calibration`,
      {
        method: "PUT",
        body: JSON.stringify(request),
      },
    ).then(unwrapApiResponse),

  delete: (cameraId: string) =>
    apiRequest<ApiResponse<CameraCalibration | null>>(
      `/cameras/${cameraId}/calibration`,
      { method: "DELETE" },
    ).then(unwrapApiResponse),
}
