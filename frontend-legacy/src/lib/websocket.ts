type JsonWebSocketOptions<T> = {
    url: string
    onMessage: (data: T) => void
    onOpen?: () => void
    onClose?: () => void
    onError?: (error: Event) => void
}

export function createJsonWebSocket<T>({
    url,
    onMessage,
    onOpen,
    onClose,
    onError,
}: JsonWebSocketOptions<T>) {
    const socket = new WebSocket(url)

    socket.addEventListener('open', () => {
        onOpen?.()
    })

    socket.addEventListener('message', (event) => {
        try {
            onMessage(JSON.parse(event.data) as T)
        } catch {
            // Ignore malformed messages so a single bad frame does not close the stream.
        }
    })

    socket.addEventListener('error', (event) => {
        onError?.(event)
    })

    socket.addEventListener('close', () => {
        onClose?.()
    })

    return socket
}
