/* r0ki 차트 공통 토큰 — 인계서 §10: 차트는 --graphic 단일 계열 명도 램프.
   진할수록 주의가 필요한 항목이다(상태 색 램프와 같은 규칙).
   색은 CSS 변수 + fillOpacity 로 조합해 주간/야간 테마 전환을 그대로 따라간다. */

/** 명도 램프 — index 0 이 가장 진함(주의도 최고) */
export const RAMP = [1, 0.68, 0.44, 0.28]

/** 축 라벨 공통 스타일 (Recharts tick) */
export const AXIS_TICK = { fill: 'var(--text-3)', fontSize: 12, fontWeight: 600 } as const

/** 숫자 축 라벨 — mono */
export const AXIS_TICK_NUM = { ...AXIS_TICK, fontFamily: 'var(--mono)' } as const
