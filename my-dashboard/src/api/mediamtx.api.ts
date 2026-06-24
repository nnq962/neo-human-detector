import { apiRequest } from "./client"

export interface CheckCameraResult {
  pathName: string
  ready: boolean
}

interface ApiResponse<T> {
  success: boolean
  message: string
  data: T
}

function unwrapApiResponse<T>(response: ApiResponse<T>): T {
  if (!response.success) {
    throw new Error(response.message || "API request failed")
  }

  return response.data
}

export const mediamtxApi = {
  checkCamera: (source: string, sourceProtocol = "tcp") =>
    apiRequest<ApiResponse<CheckCameraResult>>("/mediamtx/check-camera", {
      method: "POST",
      body: JSON.stringify({ source, sourceProtocol }),
    }).then(unwrapApiResponse),
}
