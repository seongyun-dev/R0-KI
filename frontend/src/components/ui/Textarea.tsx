import { forwardRef, type TextareaHTMLAttributes } from 'react'
import { cn } from '../../lib/cn'

export type TextareaProps = {
  invalid?: boolean
} & TextareaHTMLAttributes<HTMLTextAreaElement>

export const Textarea = forwardRef<HTMLTextAreaElement, TextareaProps>(function Textarea(
  { invalid, className, ...rest },
  ref,
) {
  return (
    <textarea
      ref={ref}
      rows={4}
      aria-invalid={invalid || undefined}
      className={cn(
        'w-full resize-y rounded-control bg-bg px-4 py-3 text-sm ring-1 ring-line transition-shadow',
        'placeholder:text-subtle focus:outline-none focus:ring-2 focus:ring-accent',
        invalid && 'ring-danger focus:ring-danger',
        className,
      )}
      {...rest}
    />
  )
})
