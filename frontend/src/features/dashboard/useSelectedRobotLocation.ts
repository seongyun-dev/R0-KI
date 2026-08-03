import { robotsApi } from '../../api/services'
import { env } from '../../config/env'
import { useApiQuery } from '../../lib/useApiQuery'
import type { ComplexMapData } from '../../types/domain'
import { toMapRobot } from './useRobotLocations'

const ROUTE_VISIBLE_STATUSES = new Set(['PATROLLING', 'OBSTACLE_STOP'])

export function useSelectedRobotLocation(
  robotId: string | number | undefined,
  map: ComplexMapData | undefined,
) {
  return useApiQuery(
    async () => {
      if (env.useMocks || robotId == null || !map) return undefined

      const response = await robotsApi.location(robotId)
      const robot = toMapRobot(response, map)
      if (!robot) return undefined

      const showRoute = ROUTE_VISIBLE_STATUSES.has(response.status)
      return {
        robot: showRoute ? robot : { ...robot, routePoints: undefined },
        showRoute,
      }
    },
    [robotId, map],
    { enabled: !env.useMocks && robotId != null && Boolean(map) },
  )
}
