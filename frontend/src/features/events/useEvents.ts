import { useCallback, useEffect } from 'react'
import { eventsApi } from '../../api/services'
import { eventDetailToDomain, eventListItemToDomain } from '../../api/mappers'
import { useApiMutation } from '../../lib/useApiMutation'
import { useApiQuery } from '../../lib/useApiQuery'
import type { ProcessingStatus } from '../../types/domain'
import type { EventListRequest, ProcessingStatusCode } from '../../api/contracts'

// UI 필터값 → 백엔드 enum. 매핑 없는 값(all 등)은 undefined → 쿼리에서 생략(전체).
// 유형·위험도 필터는 백엔드 목록 API가 아직 미지원 → 서버로 보내지 않고 보류.



/** 이벤트 목록 (1f). 서버 연동 시 useQuery(['events'])로 교체. */
export function useEvents(params: EventListRequest = {})
{
  const query = useApiQuery(
    async () => {

      const response = await eventsApi.list({
        type: params.type, 
        status: params.status,
        period: params.period,
        risk: params.risk,
        page: params.page,
        size: params.size,
        sort: params.sort,
      })
        // 유형·위험도 필터는 백엔드 미지원 → 보류 (확장 후 연결)
      return {
        ...response,
        content: response.content.map(eventListItemToDomain),
      }
    },
    [
      params.type,
      params.status,
      params.period,
      params.risk,
      params.page,
      params.size,
      params.sort?.join(','),
    ],
    { delayMs: 0 },
  )

  return {
    ...query,
    data: query.data?.content,
    page: query.data?.page ?? params.page ?? 0,
    size: query.data?.size ?? params.size ?? 10,
    totalElements: query.data?.totalElements ?? 0,
    totalPages: query.data?.totalPages ?? 0,
    first: query.data?.first ?? true,
    last: query.data?.last ?? true,
  }
}

/** 이벤트 상세 (1g). 서버 연동 시 useQuery(['event', id])로 교체. */
export function useEvent(id: string | undefined) {
  return useApiQuery(
    async () => {
      if (!id) return undefined
      return eventDetailToDomain(await eventsApi.detail(id))
    },
    [id],
    { enabled: Boolean(id), delayMs: 0 },
  )
}

export function useEvidenceImage(fileUrl: string | undefined) {
  const query = useApiQuery(
    async () => {
      if (!fileUrl) return undefined
      const blob = await eventsApi.evidenceFile(fileUrl)
      return URL.createObjectURL(blob)
    },
    [fileUrl],
    { enabled: Boolean(fileUrl) },
  )

  const objectUrl = query.data
  useEffect(
    () => () => {
      if (objectUrl?.startsWith('blob:')) URL.revokeObjectURL(objectUrl)
    },
    [objectUrl],
  )

  return query
}

const STATUS_CODE: Record<ProcessingStatus, ProcessingStatusCode> = {
  탐지: 'DETECTED',
  처리중: 'PROCESSING',
  처리완료: 'COMPLETED',
}

export function useUpdateEventStatus() {
  const update = useCallback(
    async (variables: {
      eventId: string | number
      status: ProcessingStatus
      note?: string
    }) => {

      await eventsApi.updateStatus(variables.eventId, {
        processingStatus: STATUS_CODE[variables.status],
        processingNote: variables.note ?? '',
      })
    },
    [],
  )

  return useApiMutation(update)
}
