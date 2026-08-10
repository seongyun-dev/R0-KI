import type { ButtonHTMLAttributes } from 'react'
import { cn } from '../../lib/cn'

export type IconButtonProps = {
  /** 접근성 필수 — 아이콘만 있는 버튼의 라벨 */
  label: string
  variant?: 'light' | 'dark' | 'ghost'
  size?: 'sm' | 'md'
} & ButtonHTMLAttributes<HTMLButtonElement>

const surface = {
  light: 'bg-surface text-fg hover:bg-surface-2',
  dark: 'bg-ink text-white hover:bg-card',
  ghost: 'bg-transparent text-muted hover:bg-surface hover:text-fg',
}
const sizes = { sm: 'h-8 w-8 text-sm', md: 'h-10 w-10 text-base' }

export function IconButton({ label, variant = 'ghost', size = 'md', className, children, ...rest }: IconButtonProps) {
  return (
    <button
      type="button"
      aria-label={label}
      title={label}
      className={cn(
        'grid flex-none place-items-center rounded-pill transition-colors duration-300 ease-snap disabled:pointer-events-none disabled:opacity-50',
        surface[variant],
        sizes[size],
        className,
      )}
      {...rest}
    >
      {children}
    </button>
  )
}
