import { listCameras } from './cameraApi'
import { getDetectorConfig } from './detectorApi'
import { getUartConfig } from './uartApi'
import { getZonesStateMachineConfig } from './zonesStateMachineApi'
import type { AppConfig } from '../types/config'

export async function getConfig(): Promise<AppConfig> {
    const [detectorSettings, uart, zonesStateMachine, cameras] = await Promise.all([
        getDetectorConfig(),
        getUartConfig(),
        getZonesStateMachineConfig(),
        listCameras(),
    ])
    const firstCamera = cameras[0]

    return {
        auto_start: detectorSettings.auto_start,
        detector: {
            ...detectorSettings.detector,
            ...zonesStateMachine,
        },
        uart,
        cameras,
        zones: firstCamera?.zones || [],
    }
}
