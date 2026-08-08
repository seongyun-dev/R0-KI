import type { CSSProperties } from 'react'
import type { ZoneType } from '../../types/domain'

/* 구역 색 — 온보딩 StepZones 와 동일 매핑.
   대시보드 ComplexMap 과 순찰 상세 지도가 같은 색을 쓰도록 여기 한 곳에 둔다. */
const zoneTone: Record<ZoneType, string> = {
  주차장: 'patrol',
  분리수거장: 'charge',
  출입구: 'detect',
  도착지: 'offline',
  기타: 'offline',
}

export const zoneVar = (type: ZoneType) => ({ '--z': `var(--${zoneTone[type]})` }) as CSSProperties
