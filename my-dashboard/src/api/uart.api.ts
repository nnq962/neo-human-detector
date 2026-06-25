import { apiRequest, type ApiResponse, ensureApiSuccess, unwrapApiResponse } from "./client"

export interface UartConfig {
  port: string
  baudrate: number
}

export interface UartConfigUpdate {
  port?: string
  baudrate?: number
}

export const uartApi = {
  get: () => apiRequest<ApiResponse<UartConfig>>("/uart").then(unwrapApiResponse),
  update: (data: UartConfigUpdate) =>
    apiRequest<ApiResponse<UartConfig>>("/uart", {
      method: "PATCH",
      body: JSON.stringify(data),
    }).then(ensureApiSuccess),
  send: (command: string) =>
    apiRequest<void>("/uart/send", {
      method: "POST",
      body: JSON.stringify({ command }),
    }),
}
