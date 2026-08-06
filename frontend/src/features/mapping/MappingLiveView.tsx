import { useMjpegStream } from '../dashboard/useMjpegStream'

export type MappingLiveViewProps = {
  robotId: string | number
  mappingSessionId?: string | number
  active: boolean
}

export function MappingLiveView({
  robotId,
  mappingSessionId,
  active,
}: MappingLiveViewProps) {
  const endpoint = `/live/mapping/robots/${encodeURIComponent(String(robotId))}/stream.mjpg`
  const { frameUrl, state } = useMjpegStream(robotId, {
    endpoint,
    enabled: active,
    lifecycleKey: mappingSessionId,
  })

  const statusText = !active
    ? '맵 파악을 시작하면 실시간 LiDAR 지도가 표시됩니다.'
    : state === 'idle' || state === 'connecting'
      ? 'LiDAR 지도 스트림에 연결하고 있습니다.'
      : state === 'waiting'
        ? '연결되었습니다. 첫 LiDAR 프레임을 기다리고 있습니다.'
        : state === 'offline'
          ? 'LiDAR 지도 연결에 실패했습니다. 잠시 후 다시 확인해 주세요.'
          : '실시간 LiDAR 지도를 수신하고 있습니다.'

  return (
    <section className="mapping-live" aria-label="실시간 LiDAR 지도">
      <div className="mapping-live__viewport">
        {frameUrl ? (
          <img
            className="mapping-live__frame"
            src={frameUrl}
            alt="로봇이 실시간으로 생성 중인 LiDAR 지도"
          />
        ) : (
          <div className="mapping-live__placeholder" aria-hidden="true">
            <svg viewBox="0 0 120 120">
              <circle cx="60" cy="60" r="42" />
              <circle cx="60" cy="60" r="26" />
              <path d="M60 12v96M12 60h96M26 26l68 68M94 26 26 94" />
              <circle className="mapping-live__scan" cx="60" cy="60" r="7" />
            </svg>
          </div>
        )}
      </div>
      <p
        className={`mapping-live__status mapping-live__status--${state}`}
        role="status"
        aria-live="polite"
      >
        <span aria-hidden="true" />
        {statusText}
      </p>
    </section>
  )
}
