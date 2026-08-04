import type {
  Id,
  MapDetailResponse,
  NavigationWaypointRequest,
  WaypointActionCode,
  ZoneCreateResponse,
} from '../../api/contracts'
import { isWorldPointInMap } from './mapCoordinates'

export const DEFAULT_ACCEPTANCE_RADIUS = 0.3
// Jetson의 금요일 고정 Nav2 설정(xy_goal_tolerance=0.20m)보다 작은 값은
// 저장에는 성공해도 START_PATROL에서 거절되므로 편집 계약에서 미리 차단한다.
export const MIN_ACCEPTANCE_RADIUS = 0.2
export const MAX_ACCEPTANCE_RADIUS = 1

const roundTo = (value: number, fractionDigits: number) =>
  Number(value.toFixed(fractionDigits))

export type EditableWaypoint = {
  key: string
  waypointId?: Id
  x: number
  y: number
  action: WaypointActionCode
  yaw: number | null
  acceptanceRadius: number | null
  zoneId: Id | null
}

export function toWaypointRequests(
  waypoints: EditableWaypoint[],
): NavigationWaypointRequest[] {
  return waypoints.map((waypoint, index) => ({
    sequence: index + 1,
    // Backend DB 계약과 같은 정밀도로 검증·저장해 PUT 성공 후 재조회 값이
    // 달라지거나, 브라우저 클릭 좌표가 @Digits 검증에서 거절되지 않게 한다.
    x: roundTo(waypoint.x, 3),
    y: roundTo(waypoint.y, 3),
    action: waypoint.action,
    yaw: waypoint.yaw == null ? null : roundTo(waypoint.yaw, 4),
    acceptanceRadius:
      waypoint.acceptanceRadius == null
        ? null
        : roundTo(waypoint.acceptanceRadius, 3),
    zoneId: waypoint.zoneId,
  }))
}

export function validateNavigationWaypoints(
  map: MapDetailResponse,
  waypoints: EditableWaypoint[],
  zones: ZoneCreateResponse[],
) {
  const errors: string[] = []
  if (waypoints.length === 0) return ['지도 위를 눌러 순찰 지점을 한 곳 이상 추가해 주세요.']

  const requests = toWaypointRequests(waypoints)
  if (!requests.every((waypoint, index) => waypoint.sequence === index + 1)) {
    errors.push('순찰 지점 순서는 1부터 빠짐없이 이어져야 합니다.')
  }

  const destinations = requests.filter((waypoint) => waypoint.action === 'DESTINATION')
  if (destinations.length !== 1) {
    errors.push('도착 지점은 정확히 한 곳이어야 합니다.')
  } else if (requests.at(-1)?.action !== 'DESTINATION') {
    errors.push('도착 지점은 순찰 경로의 마지막 순서여야 합니다.')
  }

  const knownZoneIds = new Set(zones.map((zone) => String(zone.zoneId)))
  requests.forEach((waypoint, index) => {
    const label = `${index + 1}번 지점`
    if (!Number.isFinite(waypoint.x) || !Number.isFinite(waypoint.y)) {
      errors.push(`${label}의 좌표가 올바르지 않습니다.`)
    } else {
      try {
        if (!isWorldPointInMap(map, waypoint)) {
          errors.push(`${label}이 지도 범위를 벗어났습니다.`)
        }
      } catch (reason) {
        errors.push(reason instanceof Error ? reason.message : '지도 좌표 메타데이터를 확인해 주세요.')
      }
    }
    if (
      waypoint.acceptanceRadius == null ||
      !Number.isFinite(waypoint.acceptanceRadius) ||
      waypoint.acceptanceRadius < MIN_ACCEPTANCE_RADIUS ||
      waypoint.acceptanceRadius > MAX_ACCEPTANCE_RADIUS
    ) {
      errors.push(
        `${label}의 도착 반경은 ${MIN_ACCEPTANCE_RADIUS.toFixed(2)}m 이상 ${MAX_ACCEPTANCE_RADIUS.toFixed(2)}m 이하여야 합니다.`,
      )
    }
    if (waypoint.yaw != null && !Number.isFinite(waypoint.yaw)) {
      errors.push(`${label}의 yaw 값이 올바르지 않습니다.`)
    }
    if (waypoint.zoneId != null && !knownZoneIds.has(String(waypoint.zoneId))) {
      errors.push(`${label}이 현재 지도에 없는 구역을 참조합니다.`)
    }
  })

  for (let index = 1; index < requests.length; index += 1) {
    const previous = requests[index - 1]
    const current = requests[index]
    const distance = Math.hypot(current.x - previous.x, current.y - previous.y)
    const requiredDistance =
      (previous.acceptanceRadius ?? DEFAULT_ACCEPTANCE_RADIUS) +
      (current.acceptanceRadius ?? DEFAULT_ACCEPTANCE_RADIUS)
    if (distance <= requiredDistance) {
      errors.push(
        `${index}번과 ${index + 1}번 지점이 너무 가깝습니다. ` +
        `두 지점 거리는 도착 반경 합(${requiredDistance.toFixed(2)}m)보다 커야 합니다.`,
      )
    }
  }

  return [...new Set(errors)]
}
