import type { BatchSize, DetectionTask, ModelSize, TrackerConfig } from './types'

export const baudrateOptions = [
    9600, 19200, 38400, 57600, 115200, 230400, 460800, 921600,
]

export const detectionTaskOptions: DetectionTask[] = ['detect', 'pose']

export const modelSizeOptions: ModelSize[] = ['nano', 'medium']

export const batchSizeOptions: BatchSize[] = [1, 2]

export const trackerOptions: TrackerConfig[] = ['bytetrack.yaml', 'botsort.yaml']
