import { useMjpegStream } from './useMjpegStream'

/* 선택한 로봇의 MJPEG 실시간 영상. */

export type R0KiLiveCamProps = {
  robotId?: string | number
}

export function R0KiLiveCam({ robotId }: R0KiLiveCamProps) {
  const { frameUrl, state, handleFrameLoad, handleFrameError } = useMjpegStream(robotId)
  const emptyMessage =
    state === 'idle'
      ? '순찰이 진행 중이지 않습니다.'
      : state === 'failed'
        ? '카메라 영상을 불러오지 못했습니다.'
        : state === 'retrying'
          ? '카메라 영상을 다시 연결하고 있습니다.'
          : '카메라 영상을 연결하고 있습니다.'

  return (
    <div className="cam">
      {frameUrl && (
        <img
          className="camstream"
          src={frameUrl}
          alt="로봇 좌우 카메라 AI 실시간 탐지 영상"
          onLoad={handleFrameLoad}
          onError={handleFrameError}
        />
      )}
      {state !== 'live' && (
        <div className="cam-empty">{emptyMessage}</div>
      )}
      <span className={`rec${state === 'live' ? '' : ' paused'}`} />
    </div>
  )
}
