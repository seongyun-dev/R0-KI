import { robots } from '../../mocks'
import { useCallback } from 'react'
import { robotResponseToDomain } from '../../api/mappers'
import { robotsApi } from '../../api/services'
import { env } from '../../config/env'
import { useApiMutation } from '../../lib/useApiMutation'
import { useApiQuery } from '../../lib/useApiQuery'
import type { RobotStatus } from '../../types/domain'

/** 로봇 목록. 서버 연동 시 useQuery(['robots'])로 교체. */
export function useRobots() {
  return useApiQuery(
    async () => {
      if (env.useMocks) return robots
      return (await robotsApi.list()).map(robotResponseToDomain)
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
      return robotResponseToDomain(await robotsApi.detail(id))
    },
    [id],
    { enabled: Boolean(id), delayMs: env.useMocks ? 350 : 0 },
  )
}

export function useUpdateRobot() {
  const update = useCallback(
    async (variables: { robotId: string | number; robotName: string; robotStatus: RobotStatus }) => {
      if (env.useMocks) return undefined
      return robotResponseToDomain(
        await robotsApi.update(variables.robotId, {
          robotName: variables.robotName,
          robotStatus: variables.robotStatus,
        }),
      )
    },
    [],
  )
  return useApiMutation(update)
}

export function useCreateRobot() {
  const create = useCallback(
    async (variables: {
      robotSerialNumber: string
      robotName: string
      model?: string
    }) => {
      if (env.useMocks) return undefined
      return robotResponseToDomain(await robotsApi.create(variables))
    },
    [],
  )
  return useApiMutation(create)
}
