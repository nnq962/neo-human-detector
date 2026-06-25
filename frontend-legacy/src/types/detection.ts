export type DetectionZoneStatus = 'EMPTY' | 'OCCUPIED' | 'PENDING_ENTER' | 'PENDING_EXIT'

export interface DetectionBoxesPayload {
    cameras: Record<string, DetectionCameraPayload>
}

export interface DetectionCameraPayload {
    timestamp: number
    camera_id: string
    camera_name: string
    resolution: {
        width: number
        height: number
    }
    count: number
    objects: DetectionObject[]
    zones?: Record<string, DetectionZoneStatus>
    zone_counts?: Record<string, number>
}

export interface DetectionObject {
    bbox: [number, number, number, number]
    conf: number
}
