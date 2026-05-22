import { apiRequest } from '../lib/http'
import type { ZonesStateMachineConfig } from '../types/config'

export type ZonesStateMachineConfigUpdatePayload = Partial<ZonesStateMachineConfig>

export function getZonesStateMachineConfig() {
    return apiRequest<ZonesStateMachineConfig>('/api/zones-state-machine')
}

export function updateZonesStateMachineConfig(config: ZonesStateMachineConfigUpdatePayload) {
    return apiRequest<ZonesStateMachineConfig>('/api/zones-state-machine', {
        method: 'PATCH',
        body: JSON.stringify(config),
    })
}

export function replaceZonesStateMachineConfig(config: ZonesStateMachineConfig) {
    return apiRequest<ZonesStateMachineConfig>('/api/zones-state-machine', {
        method: 'PUT',
        body: JSON.stringify(config),
    })
}
