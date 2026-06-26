import { apiRequest, type ApiResponse, ensureApiSuccess, unwrapApiResponse } from "./client"

export interface UartConfig {
  port: string
  baudrate: number
}

export interface UartConfigUpdate {
  port?: string
  baudrate?: number
}

export interface UartSendResult {
  sent: boolean
  command: string
}

export interface UartEvent {
  sequence: number
  timestamp: number
  type: "json" | "string"
  raw: string
  data: unknown
}

export function getUartEventsWsUrl() {
  const protocol = window.location.protocol === "https:" ? "wss:" : "ws:"
  return `${protocol}//${window.location.host}/ws/uart/events`
}

export const uartApi = {
  get: () => apiRequest<ApiResponse<UartConfig>>("/uart").then(unwrapApiResponse),
  update: (data: UartConfigUpdate) =>
    apiRequest<ApiResponse<UartConfig>>("/uart", {
      method: "PATCH",
      body: JSON.stringify(data),
    }).then(ensureApiSuccess),
  send: (command: string) =>
    apiRequest<ApiResponse<UartSendResult>>("/uart/send", {
      method: "POST",
      body: JSON.stringify({ command }),
    }).then(unwrapApiResponse),
}
