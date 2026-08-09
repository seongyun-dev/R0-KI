import type { HTMLAttributes } from 'react'
import { cn } from '../../lib/cn'

export type CardProps = {
  tone?: 'light' | 'dark'
  /** 작은 카드(rounded-card-sm) */
  compact?: boolean
} & HTMLAttributes<HTMLDivElement>

export function Card({ tone = 'light', compact, className, ...rest }: CardProps) {
  return (
    <div
      className={cn(
        compact ? 'rounded-card-sm' : 'rounded-card',
        tone === 'dark'
          ? 'bg-card text-white shadow-pop'
          : 'bg-bg ring-1 ring-line shadow-soft',
        className,
      )}
      {...rest}
    />
  )
}
