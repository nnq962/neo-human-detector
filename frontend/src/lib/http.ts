import { API_BASE_URL } from '../config/env'

type ApiRequestOptions = RequestInit & {
    headers?: HeadersInit
}

function buildApiUrl(path: string) {
    const baseUrl = API_BASE_URL?.replace(/\/$/, '')
    const normalizedPath = path.startsWith('/') ? path : `/${path}`

    return `${baseUrl}${normalizedPath}`
}

export async function apiRequest<T>(path: string, options: ApiRequestOptions = {}): Promise<T> {
    const response = await fetch(buildApiUrl(path), {
        ...options,
        headers: {
            Accept: 'application/json',
            'Content-Type': 'application/json',
            ...options.headers,
        },
    })

    const responseText = await response.text()

    if (!response.ok) {
        let message = `API request failed with HTTP ${response.status}`

        if (responseText) {
            try {
                const payload = JSON.parse(responseText) as { detail?: unknown; message?: unknown }
                const detail = payload.detail ?? payload.message

                if (typeof detail === 'string') {
                    message = detail
                }
            } catch {
                message = responseText
            }
        }

        throw new Error(message)
    }

    return (responseText ? JSON.parse(responseText) : undefined) as T
}
