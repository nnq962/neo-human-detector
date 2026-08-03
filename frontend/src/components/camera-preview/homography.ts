export type Matrix3x3 = [
  [number, number, number],
  [number, number, number],
  [number, number, number],
]

export function toMatrix3x3(matrix: number[][]): Matrix3x3 | null {
  if (
    matrix.length !== 3
    || matrix.some(
      (row) => row.length !== 3 || row.some((value) => !Number.isFinite(value)),
    )
  ) return null

  return matrix as Matrix3x3
}

export function invertMatrix3x3(matrix: Matrix3x3): Matrix3x3 | null {
  const [[a, b, c], [d, e, f], [g, h, i]] = matrix
  const determinant =
    a * (e * i - f * h)
    - b * (d * i - f * g)
    + c * (d * h - e * g)

  if (!Number.isFinite(determinant) || Math.abs(determinant) < 1e-12) {
    return null
  }

  const inverseDeterminant = 1 / determinant
  return [
    [
      (e * i - f * h) * inverseDeterminant,
      (c * h - b * i) * inverseDeterminant,
      (b * f - c * e) * inverseDeterminant,
    ],
    [
      (f * g - d * i) * inverseDeterminant,
      (a * i - c * g) * inverseDeterminant,
      (c * d - a * f) * inverseDeterminant,
    ],
    [
      (d * h - e * g) * inverseDeterminant,
      (b * g - a * h) * inverseDeterminant,
      (a * e - b * d) * inverseDeterminant,
    ],
  ]
}

export function projectPoint(
  point: [number, number],
  matrix: Matrix3x3,
): [number, number] | null {
  const [x, y] = point
  const denominator = matrix[2][0] * x + matrix[2][1] * y + matrix[2][2]
  if (!Number.isFinite(denominator) || Math.abs(denominator) < 1e-9) return null

  const projectedX = (
    matrix[0][0] * x + matrix[0][1] * y + matrix[0][2]
  ) / denominator
  const projectedY = (
    matrix[1][0] * x + matrix[1][1] * y + matrix[1][2]
  ) / denominator

  return Number.isFinite(projectedX) && Number.isFinite(projectedY)
    ? [projectedX, projectedY]
    : null
}
