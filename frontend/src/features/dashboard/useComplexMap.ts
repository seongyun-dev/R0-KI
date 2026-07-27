import { useEffect, useMemo, useState } from 'react'
import { complexMap, mapCheckpoints, mapPins, mapRobot } from '../../mocks'
import { locationEventToMapRobot, mapMonitoringToView, type MapViewData } from '../../api/mappers'
import { mapApi } from '../../api/services'
import type { MapMonitoringResponse } from '../../api/contracts'
import { env } from '../../config/env'
import { useAuthStore } from '../auth/useAuthStore'
import { useRegisteredMap } from '../onboarding/useRegisteredMap'
import { useApiQuery } from '../../lib/useApiQuery'
import type { MapRobot } from '../../types/domain'

/**
 * 단지 IoT 맵 (1c 실시간 지도).
 * 서버 연동 시:
 *  - map   → GET /complexes/:id/map (로봇이 스캔한 그리드 + 등록 구역)
 *  - robot/pins → 실시간 레이어 (폴링 또는 웹소켓)
 * 컴포넌트는 이 훅의 반환 형태만 알면 되므로 교체 지점은 여기 한 곳이다.
 */
export function useComplexMap() {
  const sessionMapId = useAuthStore((state) => state.mapId)
  const sessionRobotId = useAuthStore((state) => state.robotId)
  const mapId = sessionMapId ?? env.defaultMapId
  const robotId = sessionRobotId ?? env.defaultRobotId
  // 온보딩에서 등록한 구역 — 있으면 기본 맵 대신 이 구역을 렌더 (목업 단계)
  const registeredZones = useRegisteredMap((state) => state.zones)
  const [liveRobot, setLiveRobot] = useState<MapRobot | null>(null)

  const query = useApiQuery<{ view: MapViewData; monitoring?: MapMonitoringResponse }>(
    async () => {
      if (env.useMocks) {
        const map = registeredZones.length ? { ...complexMap, zones: registeredZones } : complexMap
        return {
          view: {
            map,
            robot: mapRobot,
            pins: mapPins,
            checkpoints: mapCheckpoints,
          },
        }
      }
      if (!mapId || !robotId) {
        throw new Error('지도 ID와 로봇 ID가 없습니다. 로그인 응답 또는 환경 설정을 확인해주세요.')
      }
      const monitoring = await mapApi.monitoring(mapId, robotId)
      return { view: mapMonitoringToView(monitoring), monitoring }
    },
    [mapId, robotId, registeredZones],
    { delayMs: env.useMocks ? 350 : 0 },
  )

  useEffect(() => {
    setLiveRobot(null)
    if (env.useMocks || !robotId || !query.data?.monitoring) return
    const controller = new AbortController()
    const monitoring = query.data.monitoring
    mapApi
      .subscribeRobotLocation(
        robotId,
        (message) => setLiveRobot(locationEventToMapRobot(message, monitoring)),
        controller.signal,
      )
      .catch(() => {
        // 초기 지도 조회는 유지한다. 재연결 정책은 백엔드 SSE 정책 확정 후 조정한다.
      })
    return () => controller.abort()
  }, [robotId, query.data?.monitoring])

  const data = useMemo(() => {
    if (!query.data) return undefined
    return {
      ...query.data.view,
      robot: liveRobot ?? query.data.view.robot,
    }
  }, [liveRobot, query.data])

  return {
    ...query,
    data,
  }
}
