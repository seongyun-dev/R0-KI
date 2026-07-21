import { patrols } from '../../mocks'
import { patrolResponseToDomain } from '../../api/mappers'
import { patrolsApi } from '../../api/services'
import { env } from '../../config/env'
import { useApiQuery } from '../../lib/useApiQuery'

/** 순찰 목록 (1d). 서버 연동 시 useQuery(['patrols'])로 교체. */
export function usePatrols(
  params: { robotId?: string; period?: string; status?: string } = {},
) {
  return useApiQuery(
    async () => {
      if (env.useMocks) {
        let list = patrols
        if (params.robotId) list = list.filter((patrol) => patrol.robotId === params.robotId)
        if (params.status && params.status !== 'all') {
          list = list.filter((patrol) => patrol.status === params.status)
        }
        if (params.period === 'today') list = list.filter((patrol) => patrol.date === '07/15')
        return list
      }
      return (
        await patrolsApi.list({
          robotId: params.robotId,
          period: params.period,
          status: params.status,
        })
      ).map((patrol) => patrolResponseToDomain(patrol))
    },
    [params.robotId, params.period, params.status],
    { delayMs: env.useMocks ? 350 : 0 },
  )
}

/** 순찰 상세 (1e). 서버 연동 시 useQuery(['patrol', id])로 교체. */
export function usePatrol(id: string | undefined) {
  return useApiQuery(
    async () => {
      if (!id) return undefined
      if (env.useMocks) return patrols.find((p) => p.id === id)
      const [patrol, path] = await Promise.all([
        patrolsApi.detail(id),
        patrolsApi.path(id).catch(() => []),
      ])
      return patrolResponseToDomain(patrol, path)
    },
    [id],
    { enabled: Boolean(id), delayMs: env.useMocks ? 350 : 0 },
  )
}
