export const AUTH_REQUIRED_EVENT = "neo-auth-required"

export function notifyAuthenticationRequired() {
  window.dispatchEvent(new Event(AUTH_REQUIRED_EVENT))
}
