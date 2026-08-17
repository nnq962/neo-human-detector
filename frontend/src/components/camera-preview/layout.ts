import type { OverlayLayout, PreviewSize, VideoSize } from "./types"

export type Point2D = { x: number; y: number }

export function computeLayout(
  preview: PreviewSize,
  video: VideoSize,
): OverlayLayout | null {
  if (!preview.width || !preview.height || !video.width || !video.height) return null

  const scale = Math.min(preview.width / video.width, preview.height / video.height)
  return {
    scale,
    offsetX: (preview.width - video.width * scale) / 2,
    offsetY: (preview.height - video.height * scale) / 2,
  }
}

export function videoPixelToPreview(
  point: Point2D,
  preview: PreviewSize,
  video: VideoSize,
): Point2D | null {
  const layout = computeLayout(preview, video)
  if (!layout) return null
  return {
    x: layout.offsetX + point.x * layout.scale,
    y: layout.offsetY + point.y * layout.scale,
  }
}

export function previewToVideoPixel(
  point: Point2D,
  preview: PreviewSize,
  video: VideoSize,
): Point2D | null {
  const layout = computeLayout(preview, video)
  if (!layout) return null
  return {
    x: (point.x - layout.offsetX) / layout.scale,
    y: (point.y - layout.offsetY) / layout.scale,
  }
}

export function normalizedVideoPointToPreview(
  point: Point2D,
  preview: PreviewSize,
  video: VideoSize,
): Point2D | null {
  return videoPixelToPreview(
    {
      x: point.x * Math.max(0, video.width - 1),
      y: point.y * Math.max(0, video.height - 1),
    },
    preview,
    video,
  )
}

export function previewPointToNormalizedVideo(
  point: Point2D,
  preview: PreviewSize,
  video: VideoSize,
): Point2D | null {
  const pixel = previewToVideoPixel(point, preview, video)
  if (!pixel) return null
  return {
    x: pixel.x / Math.max(1, video.width - 1),
    y: pixel.y / Math.max(1, video.height - 1),
  }
}

export function normalizedVideoPointToPixel(
  point: Point2D,
  video: VideoSize,
): Point2D {
  return {
    x: point.x * Math.max(0, video.width - 1),
    y: point.y * Math.max(0, video.height - 1),
  }
}
