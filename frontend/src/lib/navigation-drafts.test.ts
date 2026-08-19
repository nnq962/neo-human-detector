import { describe, expect, it } from "vitest"

import {
  clientPointToNavigationPoint,
  createNavigationDraft,
} from "@/lib/navigation-drafts"

describe("navigation drafts", () => {
  it("đổi tọa độ touch thành phần trăm trong khung camera", () => {
    expect(clientPointToNavigationPoint(300, 150, {
      left: 100,
      top: 50,
      width: 400,
      height: 200,
    })).toEqual({ x: 50, y: 50 })
  })

  it("giới hạn điểm touch trong biên khung camera", () => {
    expect(clientPointToNavigationPoint(600, 0, {
      left: 100,
      top: 50,
      width: 400,
      height: 200,
    })).toEqual({ x: 100, y: 0 })
  })

  it("tạo marker draft theo tọa độ video nguồn", () => {
    const draft = createNavigationDraft(
      { x: 75, y: 25 },
      "high",
      { width: 1920, height: 1080 },
      "draft-id",
      1_000,
    )

    expect(draft).toMatchObject({
      id: "draft-draft-id",
      kind: "draft",
      origin: null,
      x: 75,
      y: 25,
      pixelX: 1440,
      pixelY: 270,
      priority: "high",
      status: "draft",
    })
  })

  it("dùng độ phân giải 1920 × 1080 khi chưa đọc được video size", () => {
    const draft = createNavigationDraft(
      { x: 50, y: 50 },
      "low",
      null,
      "draft-id",
      1_000,
    )

    expect(draft).toMatchObject({ pixelX: 960, pixelY: 540 })
  })
})
