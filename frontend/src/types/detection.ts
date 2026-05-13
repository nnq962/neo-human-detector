export interface DetectionBoxesPayload {
    timestamp: number
    resolution: {
        width: number
        height: number
    }
    count: number
    objects: DetectionObject[]
    zones?: Record<string, string>
}

export interface DetectionObject {
    id: number
    bbox: [number, number, number, number]
    conf: number
}
