export type DisplayMaskCleanupOptions = {
  maxNoiseComponentPx?: number
  fillSurroundedHoleNeighbors?: number
  spurPasses?: number
  axisStraighteningPasses?: number
}

const NEIGHBORS = [
  [-1, -1], [0, -1], [1, -1],
  [-1, 0],           [1, 0],
  [-1, 1],  [0, 1],  [1, 1],
] as const

function validateMask(mask: Uint8Array, width: number, height: number) {
  if (!Number.isInteger(width) || !Number.isInteger(height) || width <= 0 || height <= 0) {
    throw new Error('display mask 크기가 올바르지 않습니다.')
  }
  if (mask.length !== width * height) {
    throw new Error('display mask 데이터 길이가 올바르지 않습니다.')
  }
}

function occupiedNeighborCount(mask: Uint8Array, width: number, height: number, x: number, y: number) {
  let count = 0
  for (const [dx, dy] of NEIGHBORS) {
    const nx = x + dx
    const ny = y + dy
    if (nx >= 0 && nx < width && ny >= 0 && ny < height && mask[ny * width + nx]) count += 1
  }
  return count
}

/**
 * Produce a display-only occupied mask. The source array is never mutated.
 *
 * The cleanup intentionally removes only tiny disconnected components, one-pixel
 * spurs attached to a solid mass and fully surrounded pinholes. Doors, corridors
 * and larger gaps are left untouched.
 */
export function cleanupDisplayOccupiedMask(
  source: Uint8Array,
  width: number,
  height: number,
  options: DisplayMaskCleanupOptions = {},
) {
  validateMask(source, width, height)
  const maxNoiseComponentPx = options.maxNoiseComponentPx ?? 2
  const fillSurroundedHoleNeighbors = options.fillSurroundedHoleNeighbors ?? 7
  const spurPasses = options.spurPasses ?? 2
  const axisStraighteningPasses = options.axisStraighteningPasses ?? 0
  const cleaned = source.slice()
  const visited = new Uint8Array(source.length)
  const queue = new Int32Array(source.length)

  for (let start = 0; start < source.length; start += 1) {
    if (!source[start] || visited[start]) continue
    let head = 0
    let tail = 0
    queue[tail++] = start
    visited[start] = 1
    const component: number[] = []

    while (head < tail) {
      const index = queue[head++]
      component.push(index)
      const x = index % width
      const y = Math.floor(index / width)
      for (const [dx, dy] of NEIGHBORS) {
        const nx = x + dx
        const ny = y + dy
        if (nx < 0 || nx >= width || ny < 0 || ny >= height) continue
        const neighbor = ny * width + nx
        if (!source[neighbor] || visited[neighbor]) continue
        visited[neighbor] = 1
        queue[tail++] = neighbor
      }
    }

    if (component.length <= maxNoiseComponentPx) {
      for (const index of component) cleaned[index] = 0
    }
  }

  let withoutSpurs = cleaned
  for (let pass = 0; pass < spurPasses; pass += 1) {
    const next = withoutSpurs.slice()
    for (let y = 1; y < height - 1; y += 1) {
      for (let x = 1; x < width - 1; x += 1) {
        const index = y * width + x
        if (!withoutSpurs[index] || occupiedNeighborCount(withoutSpurs, width, height, x, y) !== 1) continue
        for (const [dx, dy] of NEIGHBORS) {
          const nx = x + dx
          const ny = y + dy
          if (!withoutSpurs[ny * width + nx]) continue
          if (occupiedNeighborCount(withoutSpurs, width, height, nx, ny) >= 4) next[index] = 0
          break
        }
      }
    }
    withoutSpurs = next
  }

  let straightened = withoutSpurs
  for (let pass = 0; pass < axisStraighteningPasses; pass += 1) {
    const next = straightened.slice()
    for (let y = 1; y < height - 1; y += 1) {
      for (let x = 1; x < width - 1; x += 1) {
        const index = y * width + x
        const above = straightened[index - width - 1] + straightened[index - width] + straightened[index - width + 1]
        const below = straightened[index + width - 1] + straightened[index + width] + straightened[index + width + 1]
        const left = straightened[index - width - 1] + straightened[index - 1] + straightened[index + width - 1]
        const right = straightened[index - width + 1] + straightened[index + 1] + straightened[index + width + 1]
        const horizontalPeers = straightened[index - 1] + straightened[index + 1]
        const verticalPeers = straightened[index - width] + straightened[index + width]
        if (straightened[index]) {
          const isolatedAxisBump = (
            ((above === 0 && below === 3) || (below === 0 && above === 3)) && horizontalPeers === 0
          ) || (
            ((left === 0 && right === 3) || (right === 0 && left === 3)) && verticalPeers === 0
          )
          if (isolatedAxisBump) next[index] = 0
        } else {
          const onePixelAxisNotch = (
            ((above === 0 && below === 3) || (below === 0 && above === 3)) && horizontalPeers === 2
          ) || (
            ((left === 0 && right === 3) || (right === 0 && left === 3)) && verticalPeers === 2
          )
          if (onePixelAxisNotch) next[index] = 1
        }
      }
    }
    straightened = next
  }

  const result = straightened.slice()
  for (let y = 1; y < height - 1; y += 1) {
    for (let x = 1; x < width - 1; x += 1) {
      const index = y * width + x
      if (straightened[index]) continue
      if (occupiedNeighborCount(straightened, width, height, x, y) >= fillSurroundedHoleNeighbors) {
        result[index] = 1
      }
    }
  }
  return result
}

export function rgbaToOccupiedMask(
  rgba: Uint8ClampedArray,
  width: number,
  height: number,
  occupiedLuminanceThreshold = 96,
) {
  if (rgba.length !== width * height * 4) throw new Error('RGBA map 데이터 길이가 올바르지 않습니다.')
  const mask = new Uint8Array(width * height)
  for (let index = 0; index < mask.length; index += 1) {
    const offset = index * 4
    if (rgba[offset + 3] === 0) continue
    const luminance = rgba[offset] * 0.2126 + rgba[offset + 1] * 0.7152 + rgba[offset + 2] * 0.0722
    mask[index] = luminance <= occupiedLuminanceThreshold ? 1 : 0
  }
  return mask
}

/**
 * Return the observed part of a trinary occupancy map for display-only floors.
 *
 * ROS map previews use dark pixels for occupied space, near-white pixels for
 * free space and mid gray (normally 205) for unknown space. Keeping occupied
 * and free pixels while excluding unknown pixels gives the real mapped floor
 * silhouette without reviving the large rectangular/diamond outer slab.
 */
export function rgbaToObservedMask(
  rgba: Uint8ClampedArray,
  width: number,
  height: number,
  unknownLuminanceMin = 176,
  unknownLuminanceMax = 232,
) {
  if (rgba.length !== width * height * 4) throw new Error('RGBA map 데이터 길이가 올바르지 않습니다.')
  if (
    !Number.isFinite(unknownLuminanceMin)
    || !Number.isFinite(unknownLuminanceMax)
    || unknownLuminanceMin < 0
    || unknownLuminanceMax > 255
    || unknownLuminanceMin >= unknownLuminanceMax
  ) {
    throw new Error('unknown luminance 범위가 올바르지 않습니다.')
  }
  const mask = new Uint8Array(width * height)
  for (let index = 0; index < mask.length; index += 1) {
    const offset = index * 4
    if (rgba[offset + 3] === 0) continue
    const luminance = rgba[offset] * 0.2126 + rgba[offset + 1] * 0.7152 + rgba[offset + 2] * 0.0722
    mask[index] = luminance < unknownLuminanceMin || luminance > unknownLuminanceMax ? 1 : 0
  }
  return mask
}

export function occupiedMaskToImageData(mask: Uint8Array, width: number, height: number) {
  validateMask(mask, width, height)
  const rgba = new Uint8ClampedArray(width * height * 4)
  for (let index = 0; index < mask.length; index += 1) {
    const value = mask[index] ? 0 : 255
    const offset = index * 4
    rgba[offset] = value
    rgba[offset + 1] = value
    rgba[offset + 2] = value
    rgba[offset + 3] = 255
  }
  return new ImageData(rgba, width, height)
}

export function observedMaskToImageData(mask: Uint8Array, width: number, height: number) {
  validateMask(mask, width, height)
  const rgba = new Uint8ClampedArray(width * height * 4)
  for (let index = 0; index < mask.length; index += 1) {
    if (!mask[index]) continue
    const offset = index * 4
    rgba[offset] = 255
    rgba[offset + 1] = 255
    rgba[offset + 2] = 255
    rgba[offset + 3] = 255
  }
  return new ImageData(rgba, width, height)
}
