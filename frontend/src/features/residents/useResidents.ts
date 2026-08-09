import { useCallback } from 'react'
import { residentsApi } from '../../api/services'
import { useApiMutation } from '../../lib/useApiMutation'
import { useApiQuery } from '../../lib/useApiQuery'
import type {
  ResidentListRequest,
  ResidentNotificationUpdateRequest,
  ResidentRegisterRequest,
  ResidentUpdateRequest,
  VehicleRegisterRequest,
} from '../../api/residentContracts'

/* 입주민 관리 — 목록/상세 조회와 등록·수정 뮤테이션.
   응답이 이미 화면에 쓸 형태라 별도 도메인 매퍼를 두지 않는다.
   표시용 문자열 가공(마스킹·시각 라벨)만 여기서 한다. */

/** 목록 (GET /api/residents) */
export function useResidents(params: ResidentListRequest = {}) {
  const query = useApiQuery(
    async () => residentsApi.list(params),
    [
      params.keyword,
      params.buildingNumber,
      params.notificationEnabled,
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
    size: query.data?.size ?? params.size ?? 20,
    totalElements: query.data?.totalElements ?? 0,
    totalPages: query.data?.totalPages ?? 0,
    first: query.data?.first ?? true,
    last: query.data?.last ?? true,
  }
}

/** 동 필터 옵션 (GET /api/residents/filter-options) */
export function useResidentFilterOptions() {
  return useApiQuery(async () => residentsApi.filterOptions(), [], { delayMs: 0 })
}

/** 상세 (GET /api/residents/{residentId}) */
export function useResident(id: string | undefined) {
  const valid = Boolean(id) && Number.isFinite(Number(id))
  return useApiQuery(
    async () => {
      if (!valid || !id) return undefined
      return residentsApi.detail(id)
    },
    [id],
    { enabled: valid, delayMs: 0 },
  )
}

export function useCreateResident() {
  const create = useCallback(
    async (variables: ResidentRegisterRequest) => residentsApi.create(variables),
    [],
  )
  return useApiMutation(create)
}

export function useUpdateResident() {
  const update = useCallback(
    async (variables: { residentId: string | number; request: ResidentUpdateRequest }) =>
      residentsApi.update(variables.residentId, variables.request),
    [],
  )
  return useApiMutation(update)
}

export function useChangeResidentNotification() {
  const change = useCallback(
    async (variables: {
      residentId: string | number
      request: ResidentNotificationUpdateRequest
    }) => residentsApi.changeNotification(variables.residentId, variables.request),
    [],
  )
  return useApiMutation(change)
}

export function useAddResidentVehicle() {
  const add = useCallback(
    async (variables: { residentId: string | number; request: VehicleRegisterRequest }) =>
      residentsApi.addVehicle(variables.residentId, variables.request),
    [],
  )
  return useApiMutation(add)
}

export function useDeleteResidentVehicle() {
  const remove = useCallback(
    async (variables: { residentId: string | number; vehicleId: string | number }) =>
      residentsApi.deleteVehicle(variables.residentId, variables.vehicleId),
    [],
  )
  return useApiMutation(remove)
}

/** 목록·상세에서 공용으로 쓰는 시각 라벨 — 알림 화면과 같은 "YYYY-MM-DD HH:MM" 형태 */
export function formatDateTimeLabel(value: string | null | undefined) {
  if (!value) return '—'
  const parsed = new Date(value)
  if (Number.isNaN(parsed.getTime())) return '—'
  const pad = (n: number) => String(n).padStart(2, '0')
  return (
    `${parsed.getFullYear()}-${pad(parsed.getMonth() + 1)}-${pad(parsed.getDate())} ` +
    `${pad(parsed.getHours())}:${pad(parsed.getMinutes())}`
  )
}

const EVENT_TYPE_LABELS: Record<string, string> = {
  ILLEGAL_PARKING: '불법주차',
  UNREGISTERED_VEHICLE: '미등록 차량',
  TRASH_DETECTED: '쓰레기',
  RECYCLING_AREA_FULL: '분리수거장',
  EMERGENCY: '응급상황',
}

export function eventTypeLabel(type: string) {
  return EVENT_TYPE_LABELS[type] ?? type
}

const NOTIFICATION_STATUS_LABELS: Record<string, string> = {
  SENT: '발송완료',
  PENDING: '발송대기',
  FAILED: '발송실패',
}

export function notificationStatusLabel(status: string) {
  return NOTIFICATION_STATUS_LABELS[status] ?? status
}
