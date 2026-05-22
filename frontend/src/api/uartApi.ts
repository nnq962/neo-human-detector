import { apiRequest } from '../lib/http'
import type { UartConfig } from '../types/config'

export type UartConfigUpdatePayload = Partial<UartConfig>

export function getUartConfig() {
    return apiRequest<UartConfig>('/api/uart')
}

export function updateUartConfig(config: UartConfigUpdatePayload) {
    return apiRequest<UartConfig>('/api/uart', {
        method: 'PATCH',
        body: JSON.stringify(config),
    })
}

export function replaceUartConfig(config: UartConfig) {
    return apiRequest<UartConfig>('/api/uart', {
        method: 'PUT',
        body: JSON.stringify(config),
    })
}
