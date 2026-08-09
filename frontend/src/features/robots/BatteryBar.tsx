import { cn } from '../../lib/cn'

export type BatteryBarProps = {
  value: number
  /** 충전중 등 경고 톤 여부 */
  warning?: boolean
  className?: string
}

/** 배터리 바 + % (1c 로봇 상태 요약 · 1i 로봇 목록) */
export function BatteryBar({ value, warning, className }: BatteryBarProps) {
  return (
    <span className={cn('inline-flex items-center gap-1.5', className)}>
      <span
        aria-hidden
        className="relative inline-block h-2.5 w-9 overflow-hidden rounded-[2px] ring-1 ring-line"
      >
        <span
          className={cn('absolute bottom-0 left-0 top-0', warning ? 'bg-warning' : 'bg-success')}
          style={{ width: `${value}%` }}
        />
      </span>
      <span className="font-mono text-xs font-bold tabular" aria-label={`배터리 ${value}%`}>
        {value}%
      </span>
    </span>
  )
}
