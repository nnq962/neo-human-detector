import { apiRequest } from "./client"

export interface CheckCameraResult {
  pathName: string
  ready: boolean
}

export const mediamtxApi = {
  checkCamera: (source: string, sourceProtocol = "tcp") =>
    apiRequest<CheckCameraResult>("/mediamtx/check-camera", {
      method: "POST",
      body: JSON.stringify({ source, sourceProtocol }),
    }),
}
