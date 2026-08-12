import { useEffect, useId, useState } from 'react'
import type { MapCoordinateMetadata } from '../onboarding/mapCoordinates'
import type { IsometricProjection } from '../onboarding/mapProjection25d'
import {
  cleanupDisplayOccupiedMask,
  observedMaskToImageData,
  occupiedMaskToImageData,
  rgbaToObservedMask,
  rgbaToOccupiedMask,
} from './displayGeometry25d'

type DisplayMapMasks = {
  floor?: string
  wall?: string
}

function useDisplayMapMasks(source: string | undefined, width: number | undefined, height: number | undefined) {
  const [displayMasks, setDisplayMasks] = useState<DisplayMapMasks>({})

  useEffect(() => {
    setDisplayMasks({})
    if (!source || !width || !height || typeof window === 'undefined') return
    let disposed = false
    const objectUrls: string[] = []
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
        const cleanedWall = cleanupDisplayOccupiedMask(occupied, width, height, {
          maxNoiseComponentPx: 2,
        })
        const observed = rgbaToObservedMask(raw.data, width, height)

        const publishMask = (
          imageData: ImageData,
          key: keyof DisplayMapMasks,
        ) => {
          const maskCanvas = document.createElement('canvas')
          maskCanvas.width = width
          maskCanvas.height = height
          const maskContext = maskCanvas.getContext('2d')
          if (!maskContext) return
          maskContext.putImageData(imageData, 0, 0)
          maskCanvas.toBlob((blob) => {
            if (disposed || !blob) return
            const objectUrl = URL.createObjectURL(blob)
            objectUrls.push(objectUrl)
            setDisplayMasks((current) => ({ ...current, [key]: objectUrl }))
          }, 'image/png')
        }

        publishMask(occupiedMaskToImageData(cleanedWall, width, height), 'wall')
        publishMask(observedMaskToImageData(observed, width, height), 'floor')
      } catch {
        // CORS-tainted or unsupported images safely fall back to the source map.
      }
    }
    image.src = source

    return () => {
      disposed = true
      objectUrls.forEach((objectUrl) => URL.revokeObjectURL(objectUrl))
    }
  }, [height, source, width])

  return displayMasks
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
  const displayMasks = useDisplayMapMasks(mapImageUrl, metadata.width, metadata.height)
  const imageTransform = map25DImageTransform(projection)
  const wallImageUrl = displayMasks.wall ?? mapImageUrl

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
            <feMorphology in="threshold" operator="dilate" radius="0.28" result="outlineMask" />
            <feFlood floodColor="var(--dm25-wall-outline)" result="outlineColor" />
            <feComposite in="outlineColor" in2="outlineMask" operator="in" result="outline" />
            <feFlood floodColor={filterId === sideFilter ? 'var(--dm25-wall-side)' : 'var(--dm25-wall-top)'} result="wallColor" />
            <feComposite in="wallColor" in2="threshold" operator="in" result="wall" />
            <feMerge>
              <feMergeNode in="outline" />
              <feMergeNode in="wall" />
            </feMerge>
          </filter>
        ))}
      </defs>
      {mapImageUrl && wallImageUrl && (
        <>
          {displayMasks.floor && (
            <>
              <g transform={`translate(0 ${wallOffset * 0.18})`}>
                <image className="dm25-inner-floor-shadow" href={displayMasks.floor} width={metadata.width} height={metadata.height} preserveAspectRatio="none" transform={imageTransform} />
              </g>
              <image className="dm25-inner-floor" href={displayMasks.floor} width={metadata.width} height={metadata.height} preserveAspectRatio="none" transform={imageTransform} />
            </>
          )}
          <g className="dm25-wall-side" transform={`translate(0 ${wallOffset})`} data-cleanup={displayMasks.wall ? 'ready' : 'fallback'}>
            <image href={wallImageUrl} width={metadata.width} height={metadata.height} preserveAspectRatio="none" transform={imageTransform} filter={`url(#${sideFilter})`} />
          </g>
          <g className="dm25-wall-top" data-cleanup={displayMasks.wall ? 'ready' : 'fallback'}>
            <image href={wallImageUrl} width={metadata.width} height={metadata.height} preserveAspectRatio="none" transform={imageTransform} filter={`url(#${topFilter})`} />
          </g>
        </>
      )}
    </>
  )
}
