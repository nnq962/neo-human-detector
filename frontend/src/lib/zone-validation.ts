export function polygonArea(points: number[][]): number {
  if (points.length < 3) return 0
  return Math.abs(points.reduce((total, point, index) => {
    const next = points[(index + 1) % points.length]
    return total + point[0] * next[1] - next[0] * point[1]
  }, 0)) / 2
}

export function getPolygonValidationError(points: number[][]): string | null {
  if (points.length < 3) return "Zone cần ít nhất 3 điểm."
  const distinctPoints = new Set(points.map(([x, y]) => `${x}:${y}`))
  if (distinctPoints.size < 3) return "Zone cần ít nhất 3 điểm phân biệt."
  if (polygonArea(points) <= 0) return "Các điểm zone không được thẳng hàng."
  return null
}
