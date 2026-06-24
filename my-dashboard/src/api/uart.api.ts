import { apiRequest } from "./client"

export interface UartConfig {
  port: string
  baudrate: number
}

export interface UartConfigUpdate {
  port?: string
  baudrate?: number
}

export const uartApi = {
  get: () => apiRequest<UartConfig>("/uart"),
  update: (data: UartConfigUpdate) =>
    apiRequest<UartConfig>("/uart", {
      method: "PATCH",
      body: JSON.stringify(data),
    }),
  send: (command: string) =>
    apiRequest<void>("/uart/send", {
      method: "POST",
      body: JSON.stringify({ command }),
    }),
}
