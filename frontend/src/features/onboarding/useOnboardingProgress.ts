import { create } from 'zustand'
import { createJSONStorage, persist } from 'zustand/middleware'

export type OnboardingPhase = 'robot' | 'scan' | 'zones'
const ONBOARDING_PHASES = new Set<OnboardingPhase>(['robot', 'scan', 'zones'])

type OnboardingProgressState = {
  ownerLoginId: string | null
  phase: OnboardingPhase | null
  robotId: string | number | null
  mapId: string | number | null
  begin: (ownerLoginId: string) => void
  moveToRobot: () => void
  moveToScan: (robotId: string | number) => void
  moveToZones: (mapId: string | number) => void
  reset: () => void
}

export const useOnboardingProgress = create<OnboardingProgressState>()(
  persist(
    (set) => ({
      ownerLoginId: null,
      phase: null,
      robotId: null,
      mapId: null,
      begin: (ownerLoginId) =>
        set({
          ownerLoginId: ownerLoginId.trim(),
          phase: 'robot',
          robotId: null,
          mapId: null,
        }),
      moveToRobot: () => set({ phase: 'robot', mapId: null }),
      moveToScan: (robotId) => set({ phase: 'scan', robotId, mapId: null }),
      moveToZones: (mapId) => set({ phase: 'zones', mapId }),
      reset: () =>
        set({
          ownerLoginId: null,
          phase: null,
          robotId: null,
          mapId: null,
        }),
    }),
    {
      name: 'patrol-onboarding-progress',
      storage: createJSONStorage(() => localStorage),
      version: 2,
      migrate: (persistedState, version) => {
        const previous =
          persistedState && typeof persistedState === 'object'
            ? (persistedState as Partial<OnboardingProgressState>)
            : {}
        const ownerLoginId =
          version >= 2 && typeof previous.ownerLoginId === 'string'
            ? previous.ownerLoginId.trim()
            : null
        if (!ownerLoginId) {
          return {
            ownerLoginId: null,
            phase: null,
            robotId: null,
            mapId: null,
          }
        }
        return {
          ownerLoginId,
          phase:
            typeof previous.phase === 'string' &&
            ONBOARDING_PHASES.has(previous.phase as OnboardingPhase)
              ? (previous.phase as OnboardingPhase)
              : null,
          robotId:
            typeof previous.robotId === 'string' || typeof previous.robotId === 'number'
              ? previous.robotId
              : null,
          mapId:
            typeof previous.mapId === 'string' || typeof previous.mapId === 'number'
              ? previous.mapId
              : null,
        }
      },
      partialize: ({ ownerLoginId, phase, robotId, mapId }) => ({
        ownerLoginId,
        phase,
        robotId,
        mapId,
      }),
    },
  ),
)
