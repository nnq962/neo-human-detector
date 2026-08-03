import { useEffect, useState, type RefObject } from "react"
import type { PreviewSize } from "./types"

const EMPTY_PREVIEW_SIZE: PreviewSize = { width: 0, height: 0 }

export function usePreviewSize(containerRef: RefObject<HTMLElement | null>) {
  const [previewSize, setPreviewSize] = useState<PreviewSize>(EMPTY_PREVIEW_SIZE)

  useEffect(() => {
    const container = containerRef.current
    if (!container) return

    const update = () => {
      const bounds = container.getBoundingClientRect()
      setPreviewSize({
        width: Math.round(bounds.width),
        height: Math.round(bounds.height),
      })
    }
    const observer = new ResizeObserver(update)
    update()
    observer.observe(container)
    return () => observer.disconnect()
  }, [containerRef])

  return previewSize
}
