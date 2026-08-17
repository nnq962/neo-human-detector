import type { Camera, Zone } from "./cameras.api"
import { apiRequest, type ApiResponse, unwrapApiResponse } from "./client"
import type { RobotHeartbeatSnapshot } from "./uart.api"

export interface PublicCamera extends Omit<Camera, "stream"> {
  zones: Zone[]
}

export const publicApi = {
  listCameras: () =>
    apiRequest<ApiResponse<PublicCamera[]>>("/public/cameras")
      .then(unwrapApiResponse),
  getRobots: () =>
    apiRequest<ApiResponse<RobotHeartbeatSnapshot>>("/public/robots")
      .then(unwrapApiResponse),
}
