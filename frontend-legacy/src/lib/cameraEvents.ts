const CAMERA_CONFIG_CHANGED_EVENT = 'camera-config-changed'

export function notifyCameraConfigChanged() {
    window.dispatchEvent(new Event(CAMERA_CONFIG_CHANGED_EVENT))
}

export function subscribeCameraConfigChanged(listener: () => void) {
    window.addEventListener(CAMERA_CONFIG_CHANGED_EVENT, listener)

    return () => {
        window.removeEventListener(CAMERA_CONFIG_CHANGED_EVENT, listener)
    }
}
