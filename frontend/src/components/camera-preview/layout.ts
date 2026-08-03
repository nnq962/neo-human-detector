import type { OverlayLayout, PreviewSize, VideoSize } from "./types"

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
