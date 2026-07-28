import { useEffect, useRef, useState } from 'react'
import { mapApi } from '../../api/services'
import type { MappingStatusCode } from '../../api/contracts'
import { Button, Spinner, StatusBadge } from '../../components/ui'

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

/** Step 3/3 — 백엔드 매핑 시작 요청과 SSE 상태 구독 */
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
    <div className="flex flex-col gap-6">
      {status === 'IDLE' && (
        <div className="flex flex-col items-center gap-4 rounded-card-sm bg-surface px-6 py-12 text-center">
          <p className="text-sm text-muted">
            버튼을 누르면 로봇이 단지를 주행하며 자동으로 지도를 생성합니다.
          </p>
          <Button variant="accent" size="lg" onClick={startScan}>
            맵 파악하기
          </Button>
        </div>
      )}

      {isRunning && (
        <div className="flex flex-col items-center gap-4 rounded-card-sm bg-surface px-6 py-12 text-center">
          <Spinner className="h-6 w-6 text-accent" />
          <p className="font-semibold">{statusText[status]}</p>
          <p className="text-xs text-subtle">실시간으로 로봇 상태를 확인하고 있습니다.</p>
        </div>
      )}

      {status === 'COMPLETED' && (
        <div className="flex flex-col items-center gap-3 rounded-card-sm bg-success-soft px-6 py-10 text-center">
          <StatusBadge label="파악 완료!" bracket className="text-sm" />
          <p className="text-sm text-muted">
            {mapId == null ? '완성된 지도 정보를 확인하고 있습니다.' : '구역 지정 단계로 이동할 수 있습니다.'}
          </p>
        </div>
      )}

      {(status === 'FAILED' || status === 'CANCELLED') && (
        <div className="flex flex-col items-center gap-4 rounded-card-sm bg-danger-soft px-6 py-10 text-center">
          <p className="font-semibold text-danger">{error ?? statusText[status]}</p>
          <Button variant="outline" onClick={startScan}>다시 시도</Button>
        </div>
      )}

      <div className="flex justify-between">
        <Button variant="outline" onClick={onPrev} disabled={isRunning}>← 이전</Button>
        <Button
          variant="dark"
          withArrow="right"
          onClick={() => mapId != null && onNext(mapId)}
          disabled={!isDone}
        >
          다음: 구역 지정
        </Button>
      </div>
    </div>
  )
}
