import { apiRequest } from '../lib/http'

export type CheckCameraOptions = {
    source: string
    sourceProtocol?: string
}

export type CheckCameraResponse = {
    pathName: string
    ready: boolean
}

export async function checkCameraWithMediaMtx({
    source,
    sourceProtocol = 'tcp',
}: CheckCameraOptions) {
    return apiRequest<CheckCameraResponse>('/api/mediamtx/check-camera', {
        method: 'POST',
        body: JSON.stringify({
            source,
            sourceProtocol,
        }),
    })
}
