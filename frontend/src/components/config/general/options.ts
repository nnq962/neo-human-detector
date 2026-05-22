import type { BatchSize, DetectorMode, ModelSize, ZoneCheckMode } from './types'

export const baudrateOptions = [
    9600, 19200, 38400, 57600, 115200, 230400, 460800, 921600,
]

export const zoneCheckModeOptions: ZoneCheckMode[] = ['bottom_center', 'center']

export const detectorModeOptions: DetectorMode[] = ['head', 'person']

export const modelSizeOptions: ModelSize[] = ['nano', 'medium']

export const batchSizeOptions: BatchSize[] = [1, 2, 4]
