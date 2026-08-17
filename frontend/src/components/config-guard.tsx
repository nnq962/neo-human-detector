import {
  type ReactNode,
  type SubmitEvent,
  useEffect,
  useState,
} from "react"
import {
  AlertCircle,
  ArrowRight,
  Eye,
  EyeOff,
  LockKeyhole,
  Settings2,
  ShieldCheck,
} from "lucide-react"
import { Button } from "@/components/ui/button"
import { Card, CardContent } from "@/components/ui/card"
import { Input } from "@/components/ui/input"
import { ApiError } from "@/api/client"
import { AUTH_REQUIRED_EVENT, authApi } from "@/api/auth.api"
import { Spinner } from "@/components/ui/spinner"

const PASSWORD_INPUT_ID = "config-password"
const PASSWORD_ERROR_ID = "config-password-error"

export function ConfigGuard({ children }: { children: ReactNode }) {
  const [authenticated, setAuthenticated] = useState<boolean | null>(null)
  const [password, setPassword] = useState("")
  const [showPassword, setShowPassword] = useState(false)
  const [error, setError] = useState("")
  const [submitting, setSubmitting] = useState(false)

  useEffect(() => {
    let active = true

    authApi.getSession()
      .then((session) => {
        if (active) setAuthenticated(session.authenticated)
      })
      .catch((requestError) => {
        if (!active) return
        setAuthenticated(false)
        setError(
          requestError instanceof Error
            ? requestError.message
            : "Không thể kiểm tra phiên đăng nhập.",
        )
      })

    const requireAuthentication = () => setAuthenticated(false)
    window.addEventListener(AUTH_REQUIRED_EVENT, requireAuthentication)
    return () => {
      active = false
      window.removeEventListener(AUTH_REQUIRED_EVENT, requireAuthentication)
    }
  }, [])

  async function verify(event: SubmitEvent<HTMLFormElement>) {
    event.preventDefault()
    setError("")
    setSubmitting(true)
    try {
      const session = await authApi.login(password)
      setPassword("")
      setAuthenticated(session.authenticated)
    } catch (requestError) {
      if (requestError instanceof ApiError && requestError.status === 429) {
        setError("Đăng nhập sai quá nhiều lần. Vui lòng chờ rồi thử lại.")
      } else {
        setError(
          requestError instanceof Error
            ? requestError.message
            : "Không thể đăng nhập.",
        )
      }
    } finally {
      setSubmitting(false)
    }
  }

  if (authenticated === null) {
    return (
      <main className="grid min-h-svh place-items-center bg-[#f5f7fb] dark:bg-background">
        <div className="flex items-center gap-3 text-sm text-muted-foreground">
          <Spinner className="size-5" />
          Đang kiểm tra phiên đăng nhập...
        </div>
      </main>
    )
  }

  if (authenticated) {
    return children
  }

  return (
    <main className="relative flex min-h-svh items-center justify-center overflow-hidden bg-[#f5f7fb] p-3 sm:p-6 dark:bg-background">
      <div
        className="pointer-events-none absolute -top-32 -left-24 size-80 rounded-full bg-[#1cb0f6]/10 blur-3xl sm:size-112"
        aria-hidden="true"
      />
      <div
        className="pointer-events-none absolute -right-24 -bottom-40 size-96 rounded-full bg-[#ce82ff]/10 blur-3xl sm:size-128"
        aria-hidden="true"
      />

      <Card className="relative z-10 grid w-full max-w-4xl gap-0 overflow-hidden rounded-3xl border-2 border-white/80 bg-card py-0 shadow-[0_24px_80px_-32px_rgba(15,23,42,0.28)] md:grid-cols-2 dark:border-border">
        <section className="relative isolate overflow-hidden bg-linear-to-br from-[#159ee4] via-[#1cb0f6] to-[#7c63e7] px-6 py-6 text-white sm:px-8 sm:py-8 md:min-h-126 md:px-9 md:py-10">
          <div
            className="absolute -top-12 -right-10 -z-10 size-44 rounded-full border-24 border-white/10"
            aria-hidden="true"
          />
          <div
            className="absolute -bottom-20 -left-16 -z-10 size-52 rounded-full bg-white/10"
            aria-hidden="true"
          />
          <div
            className="absolute right-8 bottom-14 -z-10 hidden size-16 rotate-12 rounded-2xl border-2 border-white/15 md:block"
            aria-hidden="true"
          />

          <div className="flex h-full flex-col">
            <div className="flex items-center gap-2.5">
              <span className="flex size-9 items-center justify-center rounded-xl bg-white/16 shadow-sm ring-1 ring-white/25 backdrop-blur-sm">
                <Settings2 className="size-4.5" aria-hidden="true" />
              </span>
              <span className="text-xs font-bold tracking-[0.18em] text-white/90 uppercase">
                NEO Control
              </span>
            </div>

            <div className="mt-8 sm:mt-10 md:my-auto">
              <div className="mb-5 flex size-14 items-center justify-center rounded-2xl bg-white text-[#159ee4] shadow-[0_8px_24px_rgba(10,74,130,0.2)] md:size-16">
                <ShieldCheck className="size-7 md:size-8" aria-hidden="true" />
              </div>
              <h1 className="max-w-xs text-2xl leading-tight font-semibold tracking-tight sm:text-3xl md:max-w-none md:whitespace-nowrap">
                Khu vực cấu hình hệ thống
              </h1>
              <p className="mt-3 max-w-sm text-sm leading-6 text-white/78 sm:text-base">
                Xác minh quyền truy cập trước khi thay đổi camera, model và
                thiết bị kết nối.
              </p>
            </div>

            <div className="mt-7 hidden items-center gap-2 text-xs whitespace-nowrap text-white/65 md:flex">
              <LockKeyhole className="size-3.5" aria-hidden="true" />
              <span>Phiên đăng nhập tự hết hạn theo cấu hình hệ thống</span>
            </div>
          </div>
        </section>

        <CardContent className="flex flex-col justify-center p-6 sm:p-9 md:p-10">
          <div>
            <span className="inline-flex items-center gap-1.5 rounded-full bg-[#1cb0f6]/10 px-2.5 py-1 text-xs font-semibold text-[#168bc4] dark:text-[#51c7ff]">
              <LockKeyhole className="size-3" aria-hidden="true" />
              Truy cập được bảo vệ
            </span>
            <h2 className="mt-4 text-2xl font-semibold tracking-tight">
              Chào mừng trở lại
            </h2>
            <p className="mt-2 text-sm leading-6 text-muted-foreground">
              Nhập mật khẩu cấu hình để tiếp tục vào bảng điều khiển.
            </p>
          </div>

          <form className="mt-6" onSubmit={verify} noValidate>
            <div>
              <label
                htmlFor={PASSWORD_INPUT_ID}
                className="sr-only"
              >
                Mật khẩu truy cập
              </label>
              <div className="relative">
                <LockKeyhole
                  className="pointer-events-none absolute top-1/2 left-3.5 size-4.5 -translate-y-1/2 text-muted-foreground"
                  aria-hidden="true"
                />
                <Input
                  id={PASSWORD_INPUT_ID}
                  autoFocus
                  required
                  type={showPassword ? "text" : "password"}
                  autoComplete="current-password"
                  placeholder="Nhập mật khẩu"
                  value={password}
                  aria-invalid={Boolean(error)}
                  aria-describedby={error ? PASSWORD_ERROR_ID : undefined}
                  className="h-12 rounded-xl border-2 bg-background pr-12 pl-11 text-base shadow-xs transition-[border-color,box-shadow] md:text-sm"
                  onChange={(event) => {
                    setPassword(event.target.value)
                    if (error) setError("")
                  }}
                />
                <button
                  type="button"
                  className="absolute top-1/2 right-1.5 flex size-9 -translate-y-1/2 items-center justify-center rounded-lg text-muted-foreground transition-colors hover:bg-muted hover:text-foreground focus-visible:ring-3 focus-visible:ring-ring/50 focus-visible:outline-none"
                  aria-label={showPassword ? "Ẩn mật khẩu" : "Hiện mật khẩu"}
                  aria-pressed={showPassword}
                  onClick={() => setShowPassword((visible) => !visible)}
                >
                  {showPassword ? (
                    <EyeOff className="size-4.5" aria-hidden="true" />
                  ) : (
                    <Eye className="size-4.5" aria-hidden="true" />
                  )}
                </button>
              </div>

              <div className="mt-2 min-h-5">
                {error && (
                  <p
                    id={PASSWORD_ERROR_ID}
                    className="flex animate-in items-start gap-1.5 text-sm text-destructive fade-in slide-in-from-top-1"
                    role="alert"
                    aria-live="polite"
                  >
                    <AlertCircle
                      className="mt-0.5 size-4 shrink-0"
                      aria-hidden="true"
                    />
                    <span>{error}</span>
                  </p>
                )}
              </div>
            </div>

            <Button
              type="submit"
              variant="blue"
              size="lg"
              className="mt-3 h-11 w-full rounded-xl text-sm font-semibold"
              disabled={!password || submitting}
            >
              {submitting && <Spinner className="size-4" />}
              <span>{submitting ? "Đang xác minh..." : "Tiếp tục vào cấu hình"}</span>
              <ArrowRight className="size-4" aria-hidden="true" />
            </Button>
          </form>

          <p className="mt-6 text-center text-xs leading-5 text-muted-foreground md:hidden">
            Phiên đăng nhập được bảo vệ bằng cookie HttpOnly.
          </p>
        </CardContent>
      </Card>
    </main>
  )
}
