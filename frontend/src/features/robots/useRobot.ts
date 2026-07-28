import { robots } from '../../mocks'
import { useCallback } from 'react'
import { robotDetailToDomain, robotListItemToDomain } from '../../api/mappers'
import { robotsApi } from '../../api/services'
import { env } from '../../config/env'
import { useApiMutation } from '../../lib/useApiMutation'
import { useApiQuery } from '../../lib/useApiQuery'

/** 로봇 목록 (1i). 서버 연동 시 useQuery(['robots'])로 교체. */
export function useRobots() {
  return useApiQuery(
    async () => {
      if (env.useMocks) return robots
      return (await robotsApi.list()).map(robotListItemToDomain)
    },
    [],
    { delayMs: env.useMocks ? 350 : 0 },
  )
}

/** 로봇 현황 통계 (1i KPI) — 전체/순찰중/대기·충전중. */
export function useRobotStats() {
  return useApiQuery(
    async () => {
      if (env.useMocks) {
        return {
          totalCount: robots.length,
          patrollingCount: robots.filter((r) => r.status === '순찰중').length,
          idleOrChargingCount: robots.filter((r) => r.status === '대기' || r.status === '충전중').length,
        }
      }
      return robotsApi.stats()
    },
    [],
    { delayMs: env.useMocks ? 350 : 0 },
  )
}

/** 로봇 상세 (1i). 서버 연동 시 useQuery(['robot', id])로 교체. */
export function useRobot(id: string | undefined) {
  return useApiQuery(
    async () => {
      if (!id) return undefined
      if (env.useMocks) return robots.find((r) => r.id === id)
      return robotDetailToDomain(await robotsApi.detail(id))
    },
    [id],
    { enabled: Boolean(id), delayMs: env.useMocks ? 350 : 0 },
  )
}

export function useUpdateRobot() {
  const update = useCallback(
    async (variables: { robotId: string | number; robotName: string }) => {
      if (env.useMocks) return undefined
      // 백엔드 수정 요청은 name만 받는다(상태는 시스템이 관리).
      return robotsApi.update(variables.robotId, { name: variables.robotName })
    },
    [],
  )
  return useApiMutation(update)
}

export function useCreateRobot() {
  const create = useCallback(
    async (variables: { serialNumber: string; name: string }) => {
      if (env.useMocks) return undefined
      return robotsApi.create({ name: variables.name, serialNumber: variables.serialNumber })
    },
    [],
  )
  return useApiMutation(create)
}

export function useDeleteRobot() {
  const remove = useCallback(
    async (variables: { robotId: string | number }) => {
      if (env.useMocks) return undefined
      return robotsApi.delete(variables.robotId)
    },
    [],
  )
  return useApiMutation(remove)
}
