import { create } from 'zustand'
import type { PatrolEvent } from '../../types/domain'

type EmergencyEventState = {
  events: PatrolEvent[]
  addEvent: (event: PatrolEvent) => void
}

export const useEmergencyEventStore = create<EmergencyEventState>((set) => ({
  events: [],
  addEvent: (event) =>
    set((state) => ({
      events: [...state.events.filter((item) => item.id !== event.id), event],
    })),
}))
