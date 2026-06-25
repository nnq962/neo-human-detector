import { listCameras } from './cameraApi'
import { getDetectorConfig } from './detectorApi'
import { getUartConfig } from './uartApi'
import { getZoneStateMachineConfig } from './zoneStateMachineApi'
import type { AppConfig } from '../types/config'

export async function getConfig(): Promise<AppConfig> {
    const [detectorSettings, uart, zoneStateMachine, cameras] = await Promise.all([
        getDetectorConfig(),
        getUartConfig(),
        getZoneStateMachineConfig(),
        listCameras(),
    ])
    const firstCamera = cameras[0]

    return {
        auto_start: detectorSettings.auto_start,
        detection: {
            ...detectorSettings.detection,
            ...zoneStateMachine,
        },
        uart,
        cameras,
        zones: firstCamera?.zones || [],
    }
}
