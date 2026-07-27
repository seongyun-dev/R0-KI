import { events } from '../../mocks'
import { useCallback } from 'react'
import { eventsApi } from '../../api/services'
import { eventResponseToDomain } from '../../api/mappers'
import { env } from '../../config/env'
import { useApiMutation } from '../../lib/useApiMutation'
import { useApiQuery } from '../../lib/useApiQuery'
import type { ProcessingStatus } from '../../types/domain'

/** 이벤트 목록 (1f). 서버 연동 시 useQuery(['events'])로 교체. */
export function useEvents(
  params: { type?: string; status?: string; risk?: string; period?: string } = {},
) {
  return useApiQuery(
    async () => {
      if (env.useMocks) {
        let list = events
        if (params.type && params.type !== 'all') list = list.filter((event) => event.type === params.type)
        if (params.status && params.status !== 'all') list = list.filter((event) => event.status === params.status)
        if (params.risk && params.risk !== 'all') list = list.filter((event) => event.riskLevel === params.risk)
        return list
      }
      return (
        await eventsApi.list({
          eventType: params.type,
          processingStatus: params.status,
          riskLevel: params.risk,
          period: params.period,
        })
      ).map(eventResponseToDomain)
    },
    [params.type, params.status, params.risk, params.period],
    { delayMs: env.useMocks ? 350 : 0 },
  )
}

/** 이벤트 상세 (1g). 서버 연동 시 useQuery(['event', id])로 교체. */
export function useEvent(id: string | undefined) {
  return useApiQuery(
    async () => {
      if (!id) return undefined
      if (env.useMocks) return events.find((e) => e.id === id)
      return eventResponseToDomain(await eventsApi.detail(id))
    },
    [id],
    { enabled: Boolean(id), delayMs: env.useMocks ? 350 : 0 },
  )
}

export function useUpdateEventStatus() {
  const update = useCallback(
    async (variables: { eventId: string | number; status: ProcessingStatus; note?: string }) => {
      if (env.useMocks) return
      await eventsApi.updateStatus(variables.eventId, variables.status, variables.note)
    },
    [],
  )
  return useApiMutation(update)
}
