import type { HTMLAttributes } from 'react'
import { cn } from '../../lib/cn'

export type EyebrowProps = {
  tone?: 'dark' | 'light'
  bordered?: boolean
} & HTMLAttributes<HTMLSpanElement>

/** 점 + 라벨 섹션 소제목 (landing.html .eyebrow) */
export function Eyebrow({ tone = 'dark', bordered, className, children, ...rest }: EyebrowProps) {
  return (
    <span
      className={cn(
        'inline-flex items-center gap-2 text-sm font-semibold',
        tone === 'dark' ? 'text-fg/70' : 'text-white/70',
        bordered && 'rounded-pill border border-line px-4 py-1.5',
        className,
      )}
      {...rest}
    >
      <span aria-hidden className={cn('h-1.5 w-1.5 rounded-pill', tone === 'dark' ? 'bg-accent' : 'bg-accent-light')} />
      {children}
    </span>
  )
}
