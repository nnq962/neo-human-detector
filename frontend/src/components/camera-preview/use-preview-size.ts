import { useEffect, useState, type RefObject } from "react"
import type { PreviewSize } from "./types"

const EMPTY_PREVIEW_SIZE: PreviewSize = { width: 0, height: 0 }

export function usePreviewSize(containerRef: RefObject<HTMLElement | null>) {
  const [previewSize, setPreviewSize] = useState<PreviewSize>(EMPTY_PREVIEW_SIZE)

  useEffect(() => {
    const container = containerRef.current
    if (!container) return

    const update = (entry?: ResizeObserverEntry) => {
      const width = entry?.contentRect.width ?? container.clientWidth
      const height = entry?.contentRect.height ?? container.clientHeight
      setPreviewSize({
        width: Math.round(width),
        height: Math.round(height),
      })
    }
    const observer = new ResizeObserver(([entry]) => update(entry))
    update()
    observer.observe(container)
    return () => observer.disconnect()
  }, [containerRef])

  return previewSize
}
