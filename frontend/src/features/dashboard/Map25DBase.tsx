import { useEffect, useId, useState } from 'react'
import type { MapCoordinateMetadata } from '../onboarding/mapCoordinates'
import type { IsometricProjection } from '../onboarding/mapProjection25d'
import {
  cleanupDisplayOccupiedMask,
  occupiedMaskToImageData,
  rgbaToOccupiedMask,
} from './displayGeometry25d'

function useDisplayWallMask(source: string | undefined, width: number | undefined, height: number | undefined) {
  const [displayMaskUrl, setDisplayMaskUrl] = useState<string>()

  useEffect(() => {
    setDisplayMaskUrl(undefined)
    if (!source || !width || !height || typeof window === 'undefined') return
    let disposed = false
    let objectUrl: string | undefined
    const image = new Image()

    try {
      const resolved = new URL(source, window.location.href)
      if (resolved.origin !== window.location.origin) image.crossOrigin = 'anonymous'
    } catch {
      // Relative and opaque URLs can still be loaded. Canvas security is handled below.
    }

    image.onload = () => {
      try {
        const canvas = document.createElement('canvas')
        canvas.width = width
        canvas.height = height
        const context = canvas.getContext('2d', { willReadFrequently: true })
        if (!context) return
        context.drawImage(image, 0, 0, width, height)
        const raw = context.getImageData(0, 0, width, height)
        const occupied = rgbaToOccupiedMask(raw.data, width, height)
        const cleaned = cleanupDisplayOccupiedMask(occupied, width, height, {
          maxNoiseComponentPx: 3,
          spurPasses: 3,
          axisStraighteningPasses: 1,
        })
        context.putImageData(occupiedMaskToImageData(cleaned, width, height), 0, 0)
        canvas.toBlob((blob) => {
          if (disposed || !blob) return
          objectUrl = URL.createObjectURL(blob)
          setDisplayMaskUrl(objectUrl)
        }, 'image/png')
      } catch {
        // CORS-tainted or unsupported images safely fall back to the source map.
      }
    }
    image.src = source

    return () => {
      disposed = true
      if (objectUrl) URL.revokeObjectURL(objectUrl)
    }
  }, [height, source, width])

  return displayMaskUrl
}

function map25DImageTransform(projection: IsometricProjection) {
  return `matrix(${[
    projection.tileX,
    projection.tileY,
    -projection.tileX,
    projection.tileY,
    projection.offsetX,
    projection.offsetY,
  ].join(' ')})`
}

export function Map25DBase({
  metadata,
  projection,
  mapImageUrl,
  wallOffset,
}: {
  metadata: MapCoordinateMetadata
  projection: IsometricProjection
  mapImageUrl?: string
  wallOffset: number
}) {
  const filterPrefix = useId().replaceAll(':', '')
  const sideFilter = `${filterPrefix}-wall-side`
  const topFilter = `${filterPrefix}-wall-top`
  const displayWallMaskUrl = useDisplayWallMask(mapImageUrl, metadata.width, metadata.height)
  const imageTransform = map25DImageTransform(projection)
  const wallImageUrl = displayWallMaskUrl ?? mapImageUrl

  return (
    <>
      <defs>
        {[sideFilter, topFilter].map((filterId) => (
          <filter id={filterId} key={filterId} colorInterpolationFilters="sRGB">
            <feColorMatrix
              type="matrix"
              values="0 0 0 0 0  0 0 0 0 0  0 0 0 0 0  -0.333 -0.333 -0.333 0 1"
              result="occupied"
            />
            <feComponentTransfer in="occupied" result="threshold">
              <feFuncA type="discrete" tableValues="0 0 1 1" />
            </feComponentTransfer>
            <feMorphology in="threshold" operator="erode" radius="0.7" result="openedInset" />
            <feMorphology in="openedInset" operator="dilate" radius="0.7" result="opened" />
            <feMorphology in="opened" operator="dilate" radius="0.35" result="closedOutset" />
            <feMorphology in="closedOutset" operator="erode" radius="0.35" result="cleaned" />
            <feFlood floodColor={filterId === sideFilter ? 'var(--dm25-wall-side)' : 'var(--dm25-wall-top)'} result="wallColor" />
            <feComposite in="wallColor" in2="cleaned" operator="in" />
          </filter>
        ))}
      </defs>
      {mapImageUrl && wallImageUrl && (
        <>
          <image className="dm25-map-image" href={mapImageUrl} width={metadata.width} height={metadata.height} preserveAspectRatio="none" transform={imageTransform} />
          <g className="dm25-wall-side" transform={`translate(0 ${wallOffset})`} data-cleanup={displayWallMaskUrl ? 'ready' : 'fallback'}>
            <image href={wallImageUrl} width={metadata.width} height={metadata.height} preserveAspectRatio="none" transform={imageTransform} filter={`url(#${sideFilter})`} />
          </g>
          <g className="dm25-wall-top" data-cleanup={displayWallMaskUrl ? 'ready' : 'fallback'}>
            <image href={wallImageUrl} width={metadata.width} height={metadata.height} preserveAspectRatio="none" transform={imageTransform} filter={`url(#${topFilter})`} />
          </g>
        </>
      )}
    </>
  )
}
