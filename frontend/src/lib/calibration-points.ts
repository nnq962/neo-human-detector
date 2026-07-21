export interface CalibrationPointPosition {
  id: string
  label: string
  x: number
  y: number
}

export function createCalibrationPointPositions(
  size: number,
): CalibrationPointPosition[] {
  const margin = size === 2 ? 0.2 : size === 3 ? 0.15 : 0.12
  const usableSize = 1 - margin * 2
  const points: CalibrationPointPosition[] = []

  for (let row = 0; row < size; row += 1) {
    for (let column = 0; column < size; column += 1) {
      const index = row * size + column
      points.push({
        id: `point-${index + 1}`,
        label: `P${index + 1}`,
        x: margin + (column / (size - 1)) * usableSize,
        y: margin + (row / (size - 1)) * usableSize,
      })
    }
  }

  return points
}
