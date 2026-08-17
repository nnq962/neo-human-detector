import { describe, expect, it } from "vitest"

import {
  computeLayout,
  normalizedVideoPointToPreview,
  previewPointToNormalizedVideo,
  videoPixelToPreview,
} from "./layout"

describe("camera preview layout", () => {
  it("tính pillarbox cho video 4:3 trong preview 16:9", () => {
    expect(
      computeLayout(
        { width: 1600, height: 900 },
        { width: 640, height: 480 },
      ),
    ).toEqual({ scale: 1.875, offsetX: 200, offsetY: 0 })
  })

  it("tính letterbox cho video ngang trong preview dọc", () => {
    expect(
      computeLayout(
        { width: 600, height: 1000 },
        { width: 1920, height: 1080 },
      ),
    ).toEqual({ scale: 0.3125, offsetX: 0, offsetY: 331.25 })
  })

  it.each([
    [{ width: 1280, height: 720 }, { width: 1920, height: 1080 }],
    [{ width: 1600, height: 900 }, { width: 640, height: 480 }],
    [{ width: 600, height: 1000 }, { width: 1920, height: 1080 }],
  ])("round-trip normalized không bị lệch bởi viền object-contain", (preview, video) => {
    const source = { x: 0.27, y: 0.81 }
    const projected = normalizedVideoPointToPreview(source, preview, video)
    expect(projected).not.toBeNull()

    const restored = previewPointToNormalizedVideo(projected!, preview, video)
    expect(restored?.x).toBeCloseTo(source.x, 10)
    expect(restored?.y).toBeCloseTo(source.y, 10)
  })

  it("cộng đúng offset khi chiếu pixel thật lên preview", () => {
    const projected = videoPixelToPreview(
      { x: 0, y: 240 },
      { width: 1600, height: 900 },
      { width: 640, height: 480 },
    )

    expect(projected).toEqual({ x: 200, y: 450 })
  })
})
