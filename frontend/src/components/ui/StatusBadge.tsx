import type { Tone } from '../../types/domain'
import { cn } from '../../lib/cn'

// 와이어프레임 상태 라벨 → tone 매핑 (docs/components.md)
const TONE_MAP: Record<Tone, string[]> = {
  success: ['완료', '이상무', '정상', '순찰중', '온라인', '활성'],
  info: ['진행중', '수신됨', 'SCANNING'],
  warning: ['처리중', '충전중', '점검필요', '주의', '미처리'],
  danger: ['긴급', '응급상황', '침입', '탐지', '화재'],
  neutral: ['대기'],
}

export function toneOf(label: string): Tone {
  for (const [tone, labels] of Object.entries(TONE_MAP)) {
    if (labels.some((l) => label.includes(l))) return tone as Tone
  }
  return 'neutral'
}

const toneClass: Record<Tone, string> = {
  success: 'bg-success-soft text-success',
  info: 'bg-info-soft text-info',
  warning: 'bg-warning-soft text-warning',
  danger: 'bg-danger-soft text-danger',
  neutral: 'bg-surface text-muted',
}

// 위험도·상태 라벨별 색 지정 (긴급=빨강 / 탐지=하늘색 / 보통=노랑). 낮음은 미지정 → 회색(neutral)
const LABEL_CLASS: Record<string, string> = {
  긴급: 'bg-danger-soft text-danger',
  탐지: 'bg-info-soft text-info',
  보통: 'bg-warning-soft text-warning',
}

export type StatusBadgeProps = {
  label: string
  /** `[ 완료 ]` 대괄호 스타일 */
  bracket?: boolean
  className?: string
}

export function StatusBadge({ label, bracket, className }: StatusBadgeProps) {
  return (
    <span
      className={cn(
        'inline-flex items-center whitespace-nowrap rounded-pill px-2.5 py-1 text-xs font-semibold',
        LABEL_CLASS[label] ?? toneClass[toneOf(label)],
        className,
      )}
    >
      {bracket ? `[ ${label} ]` : label}
    </span>
  )
}
