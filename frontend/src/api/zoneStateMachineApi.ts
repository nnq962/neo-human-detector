import { apiRequest } from '../lib/http'
import type { ZoneStateMachineConfig } from '../types/config'

export type ZoneStateMachineConfigUpdatePayload = Partial<ZoneStateMachineConfig>

export function getZoneStateMachineConfig() {
    return apiRequest<ZoneStateMachineConfig>('/api/zone-state-machine')
}

export function updateZoneStateMachineConfig(config: ZoneStateMachineConfigUpdatePayload) {
    return apiRequest<ZoneStateMachineConfig>('/api/zone-state-machine', {
        method: 'PATCH',
        body: JSON.stringify(config),
    })
}

export function replaceZoneStateMachineConfig(config: ZoneStateMachineConfig) {
    return apiRequest<ZoneStateMachineConfig>('/api/zone-state-machine', {
        method: 'PUT',
        body: JSON.stringify(config),
    })
}
