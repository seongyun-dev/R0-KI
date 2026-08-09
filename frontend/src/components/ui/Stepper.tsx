import { cn } from '../../lib/cn'

export type StepperProps = {
  /** 예: ['계정·단지', '로봇 등록', '맵 등록'] */
  steps: string[]
  /** 0-based 현재 스텝 */
  current: number
  className?: string
}

/** 온보딩 상단 스텝 인디케이터 — [① 계정·단지] [② 로봇 등록] [③ 맵 등록] */
export function Stepper({ steps, current, className }: StepperProps) {
  return (
    <ol className={cn('flex flex-wrap items-center gap-y-2', className)}>
      {steps.map((label, i) => {
        const state = i < current ? 'done' : i === current ? 'active' : 'todo'
        return (
          <li key={label} className="flex items-center">
            {i > 0 && <span aria-hidden className="mx-2 h-px w-5 bg-line sm:w-8" />}
            <span
              aria-current={state === 'active' ? 'step' : undefined}
              className={cn(
                'inline-flex items-center gap-2 rounded-pill py-1.5 pl-1.5 pr-4 text-sm font-semibold ring-1',
                state === 'active' && 'bg-ink text-white ring-ink',
                state === 'done' && 'bg-surface text-fg ring-line',
                state === 'todo' && 'bg-bg text-muted ring-line',
              )}
            >
              <span
                className={cn(
                  'grid h-6 w-6 flex-none place-items-center rounded-pill font-mono text-xs tabular',
                  state === 'active' && 'bg-accent text-white',
                  state === 'done' && 'bg-success text-white',
                  state === 'todo' && 'bg-surface-2 text-muted',
                )}
              >
                {state === 'done' ? '✓' : i + 1}
              </span>
              {label}
            </span>
          </li>
        )
      })}
    </ol>
  )
}
