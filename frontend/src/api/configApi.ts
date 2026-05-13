import { apiRequest } from '../lib/http'
import type { AppConfig } from '../types/config'

export function getConfig() {
    return apiRequest<AppConfig>('/api/config')
}

export function updateConfig(config: AppConfig) {
    return apiRequest<{ status?: string; message?: string }>('/api/config', {
        method: 'PUT',
        body: JSON.stringify(config),
    })
}
