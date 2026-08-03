import { cn } from "@/lib/utils"
import type { StreamStatus } from "./types"

interface StreamStatusOverlayProps {
  status: StreamStatus
  errorMessage: string
  resolution: string
  hideBadges: boolean
}

export function StreamStatusOverlay({
  status,
  errorMessage,
  resolution,
  hideBadges,
}: StreamStatusOverlayProps) {
  return (
    <>
      {status !== "live" && (
        <div className="absolute inset-0 z-10 flex items-center justify-center bg-black/75">
          <div className="flex flex-col items-center gap-3 text-center">
            <div className="grid size-12 place-items-center rounded-full bg-white/10 text-lg font-bold text-white">
              {status === "connecting" ? "···" : "!"}
            </div>
            <p className="text-sm font-medium text-white">
              {status === "connecting" ? "Đang kết nối..." : "Không thể tải stream"}
            </p>
            {errorMessage && (
              <p className="max-w-xs text-xs text-white/60">{errorMessage}</p>
            )}
          </div>
        </div>
      )}

      {!hideBadges && (
        <>
          <div className="absolute left-3 top-3 z-20 rounded-md bg-black/60 px-2.5 py-1 text-xs font-medium text-white backdrop-blur-sm">
            {resolution}
          </div>
          <div className="absolute right-3 top-3 z-20 flex items-center gap-2 rounded-md bg-black/60 px-2.5 py-1 text-xs font-medium text-white backdrop-blur-sm">
            <span className="relative flex size-2">
              {status === "live" && (
                <span className="absolute inline-flex size-full animate-ping rounded-full bg-green-400 opacity-75" />
              )}
              <span className={cn("relative inline-flex size-2 rounded-full", {
                "bg-green-400": status === "live",
                "bg-amber-400": status === "connecting",
                "bg-red-400": status === "error",
              })} />
            </span>
            {status === "live" ? "Live" : status === "connecting" ? "Connecting" : "Error"}
          </div>
        </>
      )}
    </>
  )
}
