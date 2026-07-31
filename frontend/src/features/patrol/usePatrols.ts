import { patrols } from '../../mocks'
import { patrolDetailToDomain, patrolListItemToDomain } from '../../api/mappers'
import { patrolsApi, unwrapList } from '../../api/services'
import { env } from '../../config/env'
import { useApiQuery } from '../../lib/useApiQuery'

// UI 기간 필터값 → 백엔드 enum. 매핑 없는 값(all·30d 등)은 undefined → 쿼리에서 생략(전체).
const PERIOD_PARAM: Record<string, string | undefined> = {
  today: 'TODAY',
  '7d': 'LAST_7_DAYS',
}

/** 순찰 목록 (1d). 서버 연동 시 useQuery(['patrols'])로 교체. */
export function usePatrols(
  params: {
    robotId?: string
    period?: string
    status?: string
    page?: number
    size?: number
    sort?: string[]
  } = {},
) {
  const query = useApiQuery(
    async () => {
      if (env.useMocks) {
        let list = patrols
        if (params.robotId) list = list.filter((patrol) => patrol.robotId === params.robotId)
        if (params.status && params.status !== 'all') {
          list =
            params.status === 'COMPLETED'
              ? list.filter((patrol) => patrol.end != null)
              : list.filter((patrol) => patrol.status === params.status)
        }
        if (params.period === 'today') list = list.filter((patrol) => patrol.date === '07/15')
        const page = params.page ?? 0
        const size = params.size ?? 10
        const start = page * size
        return {
          content: list.slice(start, start + size),
          page,
          size,
          totalElements: list.length,
          totalPages: Math.ceil(list.length / size),
          first: page === 0,
          last: start + size >= list.length,
        }
      }
      // 백엔드 목록은 단지 전체 순찰을 반환(robotId 필터 미지원). 완료 필터는 화면에서 처리.
      const response = await patrolsApi.list({
        period: params.period ? PERIOD_PARAM[params.period] : undefined,
        status: params.status,
        page: params.page,
        size: params.size,
        sort: params.sort,
      })
      // 목록 응답이 배열로 오면 response.content 는 undefined 라 .map 에서 터진다.
      return {
        ...response,
        content: unwrapList(response).map(patrolListItemToDomain),
      }
    },
    [
      params.robotId,
      params.period,
      params.status,
      params.page,
      params.size,
      params.sort?.join(','),
    ],
    { delayMs: env.useMocks ? 350 : 0 },
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

/** 순찰 상세 (1e). 서버 연동 시 useQuery(['patrol', id])로 교체. */
export function usePatrol(id: string | undefined) {
  return useApiQuery(
    async () => {
      if (!id) return undefined
      if (env.useMocks) return patrols.find((p) => p.id === id)
      // 상세 응답에 patrolId가 없어 요청 id를 그대로 도메인 id로 사용
      return patrolDetailToDomain(await patrolsApi.detail(id), id)
    },
    [id],
    { enabled: Boolean(id), delayMs: env.useMocks ? 350 : 0 },
  )
}
