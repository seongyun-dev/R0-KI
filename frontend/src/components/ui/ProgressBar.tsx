export type ProgressBarProps = {
  /** 0~100 */
  value: number
  label?: string
  showPercent?: boolean
  className?: string
}

/** 맵 스캔 진행률 등 (온보딩 1w) */
export function ProgressBar({ value, label, showPercent = true, className }: ProgressBarProps) {
  const clamped = Math.min(100, Math.max(0, value))
  return (
    <div className={className}>
      {(label || showPercent) && (
        <div className="mb-1.5 flex items-baseline justify-between gap-2 text-sm">
          {label && <span className="font-medium">{label}</span>}
          {showPercent && <span className="font-mono text-sm font-semibold tabular">{Math.round(clamped)}%</span>}
        </div>
      )}
      <div
        role="progressbar"
        aria-valuenow={Math.round(clamped)}
        aria-valuemin={0}
        aria-valuemax={100}
        aria-label={label}
        className="h-2 overflow-hidden rounded-pill bg-surface-2"
      >
        <div
          className="h-full rounded-pill bg-accent transition-all duration-700 ease-out"
          style={{ width: `${clamped}%` }}
        />
      </div>
    </div>
  )
}
