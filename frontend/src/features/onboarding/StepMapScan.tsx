import { useEffect, useRef, useState } from 'react'
import { mapApi } from '../../api/services'
import type { MappingStatusCode } from '../../api/contracts'

export type StepMapScanProps = {
  robotId: string | number
  onPrev: () => void
  onNext: (mapId: string | number) => void
}

const statusText: Record<MappingStatusCode, string> = {
  REQUESTED: '로봇에 지도 파악을 요청했습니다.',
  MAPPING: '로봇이 단지를 주행하며 지도를 만들고 있습니다.',
  COMPLETED: '지도 파악이 완료되었습니다.',
  FAILED: '지도 파악에 실패했습니다. 다시 시도해 주세요.',
  CANCELLED: '지도 파악이 취소되었습니다.',
}

/** Step 3/3 — 백엔드 매핑 시작 요청과 SSE 상태 구독. R0Kiauth 시안 pMap 상태 A→B */
export function StepMapScan({ robotId, onPrev, onNext }: StepMapScanProps) {
  const [status, setStatus] = useState<MappingStatusCode | 'IDLE'>('IDLE')
  const [mapId, setMapId] = useState<string | number>()
  const [error, setError] = useState<string>()
  const abortRef = useRef<AbortController>()

  useEffect(() => () => abortRef.current?.abort(), [])

  const startScan = async () => {
    abortRef.current?.abort()
    const controller = new AbortController()
    abortRef.current = controller
    setError(undefined)
    setMapId(undefined)
    setStatus('REQUESTED')

    try {
      const session = await mapApi.startMapping(robotId)
      setStatus(session.mappingStatus)
      await mapApi.subscribeMapping(
        session.mappingSessionId,
        (event) => {
          setStatus(event.status)
          if (event.mapId != null) setMapId(event.mapId)
          if (
            event.status === 'COMPLETED' ||
            event.status === 'FAILED' ||
            event.status === 'CANCELLED'
          ) {
            controller.abort()
          }
        },
        controller.signal,
      )
    } catch (reason) {
      if (controller.signal.aborted) return
      setError(reason instanceof Error ? reason.message : '지도 파악 연결에 실패했습니다.')
      setStatus('FAILED')
    }
  }

  const isRunning = status === 'REQUESTED' || status === 'MAPPING'
  const isDone = status === 'COMPLETED' && mapId != null

  return (
    <div>
      {status === 'IDLE' && (
        <div className="au-panel">
          <p className="s">버튼을 누르면 로봇이 단지를 주행하며 자동으로 지도를 생성합니다.</p>
          <button type="button" className="btn btn-p" onClick={startScan}>맵 파악하기</button>
        </div>
      )}

      {isRunning && (
        <div className="au-panel">
          <span className="au-spin" role="status" aria-live="polite" aria-label="지도 파악 중" />
          <p className="t">{statusText[status]}</p>
          <p className="s">실시간으로 로봇 상태를 확인하고 있습니다.</p>
        </div>
      )}

      {status === 'COMPLETED' && (
        <div className="au-note">
          <svg viewBox="0 0 24 24"><path d="m5 13 4.5 4.5L19 7" /></svg>
          <span>
            <b>지도 파악이 완료되었습니다.</b>{' '}
            {mapId == null
              ? '완성된 지도 정보를 확인하고 있습니다.'
              : '구역 지정 단계로 이동할 수 있습니다.'}
          </span>
        </div>
      )}

      {(status === 'FAILED' || status === 'CANCELLED') && (
        <div className="au-panel">
          <p className="t bad" role="alert">{error ?? statusText[status]}</p>
          <button type="button" className="btn btn-s" onClick={startScan}>다시 시도</button>
        </div>
      )}

      <div className="au-act">
        {/* 맵은 등록된 로봇이 주행하며 그린다. 로봇을 바꾸거나 다시 등록해야 할 때
            여기서 곧장 로봇 등록으로 돌아간다(스텝 되돌리기와 같은 동작). */}
        <button
          type="button"
          className="btn btn-s btn-add"
          onClick={onPrev}
          disabled={isRunning}
          title={isRunning ? '지도 파악 중에는 이동할 수 없습니다' : undefined}
        >
          <svg viewBox="0 0 24 24"><path d="M19 12H6M13 5l-7 7 7 7" /></svg>
          로봇 등록
        </button>
        <span className="grow" />
        <button
          type="button"
          className="btn btn-p btn-add"
          onClick={() => mapId != null && onNext(mapId)}
          disabled={!isDone}
        >
          다음: 구역 지정
          <svg viewBox="0 0 24 24"><path d="M5 12h13M12 5l7 7-7 7" /></svg>
        </button>
      </div>
    </div>
  )
}
