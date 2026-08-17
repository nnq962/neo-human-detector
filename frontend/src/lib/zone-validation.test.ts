import { describe, expect, it } from "vitest"

import { getPolygonValidationError, polygonArea } from "./zone-validation"

describe("zone validation", () => {
  it("từ chối polygon hai điểm", () => {
    expect(getPolygonValidationError([[0, 0], [1, 1]])).toContain("3 điểm")
  })

  it("từ chối điểm trùng và polygon thẳng hàng", () => {
    expect(getPolygonValidationError([[0, 0], [0, 0], [1, 1]])).toContain("phân biệt")
    expect(getPolygonValidationError([[0, 0], [1, 1], [2, 2]])).toContain("thẳng hàng")
  })

  it("chấp nhận polygon lõm có diện tích", () => {
    const points = [[0, 0], [20, 0], [10, 10], [20, 20], [0, 20]]
    expect(polygonArea(points)).toBe(300)
    expect(getPolygonValidationError(points)).toBeNull()
  })
})
