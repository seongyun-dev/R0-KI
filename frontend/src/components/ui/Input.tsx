import { forwardRef, type InputHTMLAttributes } from 'react'
import { cn } from '../../lib/cn'

export type InputProps = {
  invalid?: boolean
} & InputHTMLAttributes<HTMLInputElement>

export const Input = forwardRef<HTMLInputElement, InputProps>(function Input(
  { invalid, className, ...rest },
  ref,
) {
  return (
    <input
      ref={ref}
      aria-invalid={invalid || undefined}
      className={cn(
        'w-full rounded-control bg-bg px-4 py-3 text-sm ring-1 ring-line transition-shadow',
        'placeholder:text-subtle focus:outline-none focus:ring-2 focus:ring-accent',
        'disabled:bg-surface disabled:text-muted',
        invalid && 'ring-danger focus:ring-danger',
        className,
      )}
      {...rest}
    />
  )
})
