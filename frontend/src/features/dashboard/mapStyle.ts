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

/** 지도 마커(물방울) — 팁이 원점, 위로 부풀어 오르는 풍선. 접선점을 계산해 꼬리를 잇는다 */
export function pinPath(r: number, h: number) {
  const len = Math.sqrt(h * h - r * r)
  const a = Math.asin(r / h)
  const tx = len * Math.sin(a)
  const ty = -len * Math.cos(a)
  return `M0 0 L${tx.toFixed(2)} ${ty.toFixed(2)} A${r} ${r} 0 1 0 ${(-tx).toFixed(2)} ${ty.toFixed(2)} Z`
}
