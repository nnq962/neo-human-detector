import type { AppConfig } from '../../../types/config'

export type ZoneCheckMode = 'bottom_center' | 'center'
export type ModelSize = 'nano' | 'medium'
export type BatchSize = 1 | 2 | 4
export type SelectValue = string | number

export type GeneralConfigState = Omit<AppConfig, 'cameras' | 'zones'> & {
    detector: Omit<AppConfig['detector'], 'batch_size' | 'model_size' | 'zone_check_mode'> & {
        batch_size: BatchSize
        model_size: ModelSize
        zone_check_mode: ZoneCheckMode
    }
}

export type DetectorConfig = GeneralConfigState['detector']
export type UartConfigState = GeneralConfigState['uart']
export type CameraConfigState = AppConfig['cameras'][number]
