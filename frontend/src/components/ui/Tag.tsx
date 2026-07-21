import type { HTMLAttributes } from 'react'
import { cn } from '../../lib/cn'

export type TagProps = {
  tone?: 'light' | 'dark'
} & HTMLAttributes<HTMLSpanElement>

export function Tag({ tone = 'light', className, ...rest }: TagProps) {
  return (
    <span
      className={cn(
        'inline-flex items-center gap-1.5 rounded-pill px-4 py-1.5 text-xs font-medium',
        tone === 'dark' ? 'text-white ring-1 ring-white/25' : 'text-fg ring-1 ring-line',
        className,
      )}
      {...rest}
    />
  )
}
