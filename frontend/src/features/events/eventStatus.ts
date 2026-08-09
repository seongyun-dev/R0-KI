/* 이벤트 처리 상태 표기 — 이벤트 관리 목록과 순찰 상세 타임라인이 같이 쓴다.
   두 화면이 각자 매핑을 들고 있으면 색 체계가 갈라진다(실제로 순찰 상세에서
   '탐지'와 '처리중'이 같은 색으로 보이던 원인이다). */

/** `.st[data-status]` 배지에 넘길 코드. 이벤트가 아닌 기록(이상무 등)은 undefined */
export type EventStatusCode = 'detected' | 'processing' | 'completed'

const STATUS_CODE: Record<string, EventStatusCode> = {
  탐지: 'detected',
  처리중: 'processing',
  처리완료: 'completed',
}

export const eventStatusCode = (status?: string | null): EventStatusCode | undefined =>
  status == null ? undefined : STATUS_CODE[status]

/** 배지 밖에서 상태 색이 필요할 때(타임라인 왼쪽 점 등) — 배지 배경과 같은 토큰 */
const STATUS_COLOR: Record<EventStatusCode, string> = {
  detected: 'var(--st-patrol)',
  processing: 'var(--st-charge)',
  completed: 'var(--st-idle)',
}

export const eventStatusColor = (status?: string | null) => {
  const code = eventStatusCode(status)
  return code ? STATUS_COLOR[code] : undefined
}
