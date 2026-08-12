import { flushSync } from "react-dom"
import { useLocation } from "react-router-dom"
import { useTheme } from "next-themes"
import { Moon, Sun } from "lucide-react"
import { SidebarTrigger } from "@/components/ui/sidebar"
import { Button } from "@/components/ui/button"
import { HardwareMetricsIndicator } from "@/components/hardware-metrics-indicator"
import { RuntimeStatusIndicator } from "@/components/runtime-status"
import { cn } from "@/lib/utils"
import { useCameras } from "@/hooks/use-cameras"

const SEGMENT_LABELS: Record<string, string> = {
  cameras: "Cameras",
  calibration: "Calibration",
  detection: "Detection",
  "zone-state-machine": "Zone State Machine",
  "re-id": "Re-ID",
  uart: "UART",
}

function useBreadcrumbs() {
  const { pathname } = useLocation()
  const { data: cameras } = useCameras()

  if (pathname === "/") return ["Dashboard"]

  const segments = pathname
    .split("/")
    .filter(Boolean)

  const breadcrumbSegments =
    segments[0] === "calibration" && segments[1] === "cameras"
      ? [segments[0], ...segments.slice(2)]
      : segments

  return breadcrumbSegments.map((seg) => {
      const camera = cameras?.find((c) => c.id === seg)
      if (camera) return camera.name
      return SEGMENT_LABELS[seg] ?? seg
    })
}

function ThemeToggle() {
  const { resolvedTheme, setTheme } = useTheme()

  const toggleTheme = () => {
    const nextTheme = resolvedTheme === "dark" ? "light" : "dark"
    const prefersReducedMotion = window.matchMedia(
      "(prefers-reduced-motion: reduce)"
    ).matches

    if (!document.startViewTransition || prefersReducedMotion) {
      setTheme(nextTheme)
      return
    }

    document.startViewTransition(() => {
      flushSync(() => setTheme(nextTheme))
    })
  }

  return (
    <Button
      variant="outline"
      size="icon-sm"
      data-theme-toggle
      onClick={toggleTheme}
    >
      <Sun className="scale-100 transition-transform dark:scale-0" />
      <Moon className="absolute scale-0 transition-transform dark:scale-100" />
      <span className="sr-only">Toggle theme</span>
    </Button>
  )
}

export function AppHeader() {
  const breadcrumbs = useBreadcrumbs()

  return (
    <header className="sticky top-0 z-40 flex h-14 min-w-0 items-center gap-3 border-b-2 border-input bg-background px-4">
      <SidebarTrigger />

      <div className="h-4 w-px shrink-0 bg-border" />

      <nav className="flex min-w-0 flex-1 items-center gap-1.5 overflow-hidden whitespace-nowrap text-sm">
        {breadcrumbs.map((label, i) => (
          <span key={i} className="flex min-w-0 items-center gap-1.5">
            {i > 0 && <span className="text-muted-foreground/40">/</span>}
            <span
              className={cn(
                "truncate",
                i < breadcrumbs.length - 1
                  ? "text-muted-foreground"
                  : "font-medium",
              )}
            >
              {label}
            </span>
          </span>
        ))}
      </nav>

      <div className="ml-auto flex shrink-0 items-center gap-3">
        <HardwareMetricsIndicator />
        <RuntimeStatusIndicator />
        <ThemeToggle />
      </div>
    </header>
  )
}
