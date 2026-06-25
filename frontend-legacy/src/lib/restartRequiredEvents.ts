const RESTART_REQUIRED_EVENT = 'restart-required-changed'
const RESTART_REQUIRED_STORAGE_KEY = 'neo-human-detector.restart-required'

export function getRestartRequired() {
    return window.localStorage.getItem(RESTART_REQUIRED_STORAGE_KEY) === 'true'
}

export function setRestartRequired(required: boolean) {
    window.localStorage.setItem(RESTART_REQUIRED_STORAGE_KEY, required ? 'true' : 'false')
    window.dispatchEvent(new Event(RESTART_REQUIRED_EVENT))
}

export function notifyRestartRequired() {
    setRestartRequired(true)
}

export function clearRestartRequired() {
    setRestartRequired(false)
}

export function subscribeRestartRequiredChanged(listener: () => void) {
    window.addEventListener(RESTART_REQUIRED_EVENT, listener)

    return () => {
        window.removeEventListener(RESTART_REQUIRED_EVENT, listener)
    }
}
