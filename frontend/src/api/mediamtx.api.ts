import { apiRequest, type ApiResponse, unwrapApiResponse } from "./client"

export interface CheckCameraResult {
  pathName: string
  ready: boolean
}

export const mediamtxApi = {
  checkCamera: (source: string, sourceProtocol = "tcp") =>
    apiRequest<ApiResponse<CheckCameraResult>>("/mediamtx/check-camera", {
      method: "POST",
      body: JSON.stringify({ source, sourceProtocol }),
    }).then(unwrapApiResponse),
}
