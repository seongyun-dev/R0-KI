import { useState } from 'react'
import { ComplexMap, type ComplexMapProps } from './ComplexMap'
import { ComplexMap25D } from './ComplexMap25D'
import { complexMapCoordinateMetadata } from './mapCoordinateMetadata'

export function MonitoringMap(props: ComplexMapProps) {
  const [requestedMode, setRequestedMode] = useState<'25d' | '2d'>('25d')
  const supports25d = Boolean(complexMapCoordinateMetadata(props.map))
  const mode = supports25d ? requestedMode : '2d'

  return (
    <div className="monitoring-map">
      <div className="monitoring-map-modes" aria-label="지도 보기 방식">
        <button
          type="button"
          aria-pressed={mode === '25d'}
          disabled={!supports25d}
          onClick={() => setRequestedMode('25d')}
        >
          2.5D
        </button>
        <button
          type="button"
          aria-pressed={mode === '2d'}
          onClick={() => setRequestedMode('2d')}
        >
          2D
        </button>
      </div>
      {mode === '25d' ? <ComplexMap25D {...props} /> : <ComplexMap {...props} />}
    </div>
  )
}
