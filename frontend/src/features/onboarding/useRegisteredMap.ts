import { create } from 'zustand'
import { persist } from 'zustand/middleware'
import type { Zone } from '../../types/domain'

/**
 * 온보딩(1y)에서 등록한 구역을 보관 — 대시보드 지도(1c)가 이를 읽어 렌더한다.
 * 목업 단계 저장소. 서버 연동 시 GET /complexes/:id/map 응답으로 대체된다.
 */
type RegisteredMapState = {
  zones: Zone[]
  setZones: (zones: Zone[]) => void
  reset: () => void
}

export const useRegisteredMap = create<RegisteredMapState>()(
  persist(
    (set) => ({
      zones: [],
      setZones: (zones) => set({ zones }),
      reset: () => set({ zones: [] }),
    }),
    {
      name: 'patrol-registered-map',
      version: 1,
      migrate: (persistedState) => {
        const previous =
          persistedState && typeof persistedState === 'object'
            ? (persistedState as Partial<RegisteredMapState>)
            : {}
        return { zones: Array.isArray(previous.zones) ? previous.zones : [] }
      },
      partialize: ({ zones }) => ({ zones }),
    },
  ),
)
