import { useRef, type ReactNode } from 'react'
import { createPortal } from 'react-dom'
import { cn } from '../../lib/cn'
import { useDialog, useEnterTransition } from '../../lib/useDialog'
import { CloseIcon } from '../icons'
import { IconButton } from './IconButton'

export type ModalProps = {
  open: boolean
  onClose: () => void
  title?: string
  className?: string
  children: ReactNode
}

export function Modal({ open, onClose, title, className, children }: ModalProps) {
  const panelRef = useRef<HTMLDivElement>(null)
  useDialog(open, onClose, panelRef)
  const shown = useEnterTransition(open)

  if (!open) return null
  return createPortal(
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4">
      <div
        aria-hidden
        onClick={onClose}
        className={cn(
          'absolute inset-0 bg-ink/40 backdrop-blur-sm transition-opacity duration-300',
          shown ? 'opacity-100' : 'opacity-0',
        )}
      />
      <div
        ref={panelRef}
        role="dialog"
        aria-modal="true"
        aria-label={title}
        tabIndex={-1}
        className={cn(
          'relative w-full max-w-md rounded-card bg-bg p-7 shadow-pop transition-all duration-300 ease-out',
          shown ? 'translate-y-0 opacity-100' : 'translate-y-4 opacity-0',
          className,
        )}
      >
        <div className={cn('flex items-start justify-between gap-4', title && 'mb-5')}>
          {title && <h2 className="text-lg font-bold">{title}</h2>}
          <IconButton label="닫기" size="sm" className="-mr-2 -mt-1 ml-auto" onClick={onClose}>
            <CloseIcon />
          </IconButton>
        </div>
        {children}
      </div>
    </div>,
    document.body,
  )
}
