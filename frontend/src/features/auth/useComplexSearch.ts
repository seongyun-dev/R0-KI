import { complexes } from '../../mocks'
import { useApiQuery } from '../../lib/useApiQuery'
import { authApi } from '../../api/services'
import { complexResponseToDomain } from '../../api/mappers'
import { env } from '../../config/env'

/** 아파트단지 검색 (1t 모달 · 온보딩 기존 단지 감지) — 이름/주소 부분 일치. */
export function useComplexSearch(keyword: string, options: { enabled?: boolean } = {}) {
  return useApiQuery(
    async () => {
      const q = keyword.trim()
      if (env.useMocks) {
        if (!q) return complexes
        return complexes.filter((c) => c.name.includes(q) || c.roadAddress.includes(q))
      }
      return (await authApi.searchComplexes(q)).map(complexResponseToDomain)
    },
    [keyword],
    { delayMs: env.useMocks ? 350 : 0, enabled: options.enabled },
  )
}
