import type { VideoSize } from "@/components/camera-preview/types"
import type {
  NavigationTask,
  NavigationTaskPriority,
} from "@/lib/navigation-tasks"

export interface NavigationPoint {
  x: number
  y: number
}

export interface NavigationBounds {
  left: number
  top: number
  width: number
  height: number
}

const DEFAULT_VIDEO_SIZE: VideoSize = { width: 1920, height: 1080 }

export function clientPointToNavigationPoint(
  clientX: number,
  clientY: number,
  bounds: NavigationBounds,
): NavigationPoint | null {
  if (bounds.width <= 0 || bounds.height <= 0) return null
  return {
    x: Math.min(100, Math.max(0, ((clientX - bounds.left) / bounds.width) * 100)),
    y: Math.min(100, Math.max(0, ((clientY - bounds.top) / bounds.height) * 100)),
  }
}

export function createNavigationDraft(
  point: NavigationPoint,
  priority: NavigationTaskPriority,
  videoSize: VideoSize | null,
  id: string = crypto.randomUUID(),
  now = Date.now(),
): NavigationTask {
  const sourceSize = videoSize ?? DEFAULT_VIDEO_SIZE

  return {
    id: `draft-${id}`,
    displayId: "Nháp",
    kind: "draft",
    origin: null,
    zoneName: null,
    x: point.x,
    y: point.y,
    pixelX: Math.round((point.x / 100) * sourceSize.width),
    pixelY: Math.round((point.y / 100) * sourceSize.height),
    createdAt: new Date(now),
    completedAt: null,
    isFading: false,
    priority,
    status: "draft",
  }
}
