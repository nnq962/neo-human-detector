import type { AppConfig } from '../../../types/config'

export type DetectionTask = 'detect' | 'pose'
export type ModelSize = 'nano' | 'medium'
export type BatchSize = 1 | 2
export type TrackerConfig = 'bytetrack.yaml' | 'botsort.yaml'
export type SelectValue = string | number

export type GeneralConfigState = Omit<AppConfig, 'cameras' | 'zones'> & {
    detection: Omit<AppConfig['detection'], 'batch_size' | 'model_size'> & {
        batch_size: BatchSize
        model_size: ModelSize
    }
}

export type DetectionConfig = GeneralConfigState['detection']
export type UartConfigState = GeneralConfigState['uart']
export type CameraConfigState = AppConfig['cameras'][number]
