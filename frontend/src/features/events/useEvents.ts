import { events } from '../../mocks'
import { useCallback, useEffect } from 'react'
import { eventsApi } from '../../api/services'
import { eventDetailToDomain, eventListItemToDomain } from '../../api/mappers'
import { env } from '../../config/env'
import { useApiMutation } from '../../lib/useApiMutation'
import { useApiQuery } from '../../lib/useApiQuery'
import type { EventType, ProcessingStatus, RiskLevel } from '../../types/domain'
import type { EventListRequest, ProcessingStatusCode } from '../../api/contracts'

// UI 필터값 → 백엔드 enum. 매핑 없는 값(all 등)은 undefined → 쿼리에서 생략(전체).
// 유형·위험도 필터는 백엔드 목록 API가 아직 미지원 → 서버로 보내지 않고 보류.

/* 목업 필터용 코드 → 한글 라벨 (매퍼와 같은 매핑) */
const MOCK_TYPE: Record<string, EventType> = {
  ILLEGAL_PARKING: '불법주차',
  UNREGISTERED_VEHICLE: '불법주차',
  TRASH_DETECTED: '쓰레기',
  RECYCLING_AREA_FULL: '쓰레기',
  EMERGENCY: '응급상황',
}
const MOCK_STATUS: Record<string, ProcessingStatus> = {
  DETECTED: '탐지',
  PROCESSING: '처리중',
  COMPLETED: '처리완료',
}
const MOCK_RISK: Record<string, RiskLevel> = {
  LOW: '낮음',
  NORMAL: '보통',
  EMERGENCY: '긴급',
}

/** 이벤트 목록 (1f). 서버 연동 시 useQuery(['events'])로 교체. */
export function useEvents(params: EventListRequest = {})
{
  return useApiQuery(
    async () => {
      if (env.useMocks) {
        // 기간(period) 필터는 목업에 날짜가 없어 적용하지 않는다 — 유형·상태·위험도만
        const filtered = events
          .filter((e) => !params.type || MOCK_TYPE[params.type] === e.type)
          .filter((e) => !params.status || MOCK_STATUS[params.status] === e.status)
          .filter((e) => !params.risk || MOCK_RISK[params.risk] === e.riskLevel)
          .sort((a, b) => b.time.localeCompare(a.time)) // 최신순
        const page = params.page ?? 0
        const size = params.size ?? filtered.length
        return filtered.slice(page * size, page * size + size)
      }

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
      return response.content.map(eventListItemToDomain)
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
    { delayMs: env.useMocks ? 350 : 0 },
  )
}

/** 이벤트 상세 (1g). 서버 연동 시 useQuery(['event', id])로 교체. */
export function useEvent(id: string | undefined) {
  return useApiQuery(
    async () => {
      if (!id) return undefined
      if (env.useMocks) return events.find((e) => e.id === id)
      return eventDetailToDomain(await eventsApi.detail(id))
    },
    [id],
    { enabled: Boolean(id), delayMs: env.useMocks ? 350 : 0 },
  )
}

export function useEvidenceImage(fileUrl: string | undefined) {
  const query = useApiQuery(
    async () => {
      if (!fileUrl) return undefined
      if (env.useMocks) return fileUrl
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
      if (env.useMocks) return

      await eventsApi.updateStatus(variables.eventId, {
        processingStatus: STATUS_CODE[variables.status],
        processingNote: variables.note ?? '',
      })
    },
    [],
  )

  return useApiMutation(update)
}
