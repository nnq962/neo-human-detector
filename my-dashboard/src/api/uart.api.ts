import { apiRequest } from "./client"

export interface UartConfig {
  port: string
  baudrate: number
}

export interface UartConfigUpdate {
  port?: string
  baudrate?: number
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
