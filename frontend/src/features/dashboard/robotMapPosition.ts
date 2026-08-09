import type { MapRobot, Robot } from '../../types/domain'

/** 대시보드에서 고른 로봇의 지도 위치.
 *  목업은 로봇별 고정 좌표(mapRobots)를 쓴다.
 *  실서버는 아직 지도 응답에 로봇 한 대의 좌표만 들어와, 그 로봇일 때만 매칭한다.
 *  (로봇별 실시간 좌표는 GET /api/robots/location/events(SSE) 연동 후 여기만 교체하면 된다.) */
export function robotMapPosition(
  robot: Robot | undefined,
  mapRobotFromServer?: MapRobot,
): MapRobot | undefined {
  if (!robot) return undefined



  if (!mapRobotFromServer) return undefined
  const sameRobot =
    mapRobotFromServer.id === robot.id ||
    mapRobotFromServer.id === String(robot.backendId ?? '') ||
    mapRobotFromServer.name === robot.name
  return sameRobot ? { ...mapRobotFromServer, name: robot.name } : undefined
}
