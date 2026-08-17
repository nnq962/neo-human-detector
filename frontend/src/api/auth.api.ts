import { apiRequest } from "./client"
export {
  AUTH_REQUIRED_EVENT,
  notifyAuthenticationRequired,
} from "@/lib/auth-events"

export interface AuthSession {
  authenticated: boolean
  enabled: boolean
  configured: boolean
}

export const authApi = {
  getSession: () => apiRequest<AuthSession>("/auth/session"),
  login: (password: string) =>
    apiRequest<AuthSession>("/auth/login", {
      method: "POST",
      body: JSON.stringify({ password }),
    }),
  logout: () =>
    apiRequest<AuthSession>("/auth/logout", { method: "POST" }),
}
