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

    if (!response.ok) {
        throw new Error(`API request failed with HTTP ${response.status}`)
    }

    const responseText = await response.text()

    return (responseText ? JSON.parse(responseText) : undefined) as T
}
