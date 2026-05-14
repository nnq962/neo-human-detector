export type DetectionZoneStatus = 'EMPTY' | 'OCCUPIED' | 'PENDING_ENTER' | 'PENDING_EXIT'

export interface DetectionBoxesPayload {
    timestamp: number
    resolution: {
        width: number
        height: number
    }
    count: number
    objects: DetectionObject[]
    zones?: Record<string, DetectionZoneStatus>
}

export interface DetectionObject {
    bbox: [number, number, number, number]
    conf: number
}
