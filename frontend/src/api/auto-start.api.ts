import { apiRequest, type ApiResponse, unwrapApiResponse } from "./client"


export interface AutoStartConfig {
  auto_start: boolean
}

export type AutoStartConfigUpdate = Partial<AutoStartConfig>


export const autoStartApi = {
  get: () =>
    apiRequest<ApiResponse<AutoStartConfig>>("/auto-start").then(unwrapApiResponse),

  update: (data: AutoStartConfigUpdate) =>
    apiRequest<ApiResponse<AutoStartConfig>>("/auto-start", {
      method: "PATCH",
      body: JSON.stringify(data),
    }).then(unwrapApiResponse),
}
