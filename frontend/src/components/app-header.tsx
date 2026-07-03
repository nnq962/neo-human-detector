import { useLocation } from "react-router-dom"
import { useTheme } from "next-themes"
import { Moon, Sun } from "lucide-react"
import { SidebarTrigger } from "@/components/ui/sidebar"
import { Button } from "@/components/ui/button"
import { cn } from "@/lib/utils"
import { useCameras } from "@/hooks/use-cameras"

const SEGMENT_LABELS: Record<string, string> = {
  cameras: "Cameras",
  detection: "Detection",
  "zone-state-machine": "Zone State Machine",
  "re-id": "Re-ID",
  uart: "UART",
}

function useBreadcrumbs() {
  const { pathname } = useLocation()
  const { data: cameras } = useCameras()

  if (pathname === "/") return ["Dashboard"]

  return pathname
    .split("/")
    .filter(Boolean)
    .map((seg) => {
      const camera = cameras?.find((c) => c.id === seg)
      if (camera) return camera.name
      return SEGMENT_LABELS[seg] ?? seg
    })
}

function ThemeToggle() {
  const { resolvedTheme, setTheme } = useTheme()

  return (
    <Button
      variant="ghost"
      size="icon"
      className="size-8"
      onClick={() => setTheme(resolvedTheme === "dark" ? "light" : "dark")}
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
    <header className="sticky top-0 z-40 flex h-14 items-center gap-3 border-b bg-background px-4">
      <SidebarTrigger />

      <div className="h-4 w-px shrink-0 bg-border" />

      <nav className="flex items-center gap-1.5 text-sm">
        {breadcrumbs.map((label, i) => (
          <span key={i} className="flex items-center gap-1.5">
            {i > 0 && <span className="text-muted-foreground/40">/</span>}
            <span className={cn(i < breadcrumbs.length - 1 ? "text-muted-foreground" : "font-medium")}>
              {label}
            </span>
          </span>
        ))}
      </nav>

      <div className="ml-auto flex items-center gap-3">
        <ThemeToggle />
      </div>
    </header>
  )
}
