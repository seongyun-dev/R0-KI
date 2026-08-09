import { useRef, type ReactNode } from 'react'
import { createPortal } from 'react-dom'
import { cn } from '../../lib/cn'
import { useDialog, useEnterTransition } from '../../lib/useDialog'
import { CloseIcon } from '../icons'
import { IconButton } from './IconButton'

export type DrawerProps = {
  open: boolean
  onClose: () => void
  title?: string
  className?: string
  children: ReactNode
}

/** 우측 슬라이드 패널 (로봇 수정 1k) */
export function Drawer({ open, onClose, title, className, children }: DrawerProps) {
  const panelRef = useRef<HTMLDivElement>(null)
  useDialog(open, onClose, panelRef)
  const shown = useEnterTransition(open)

  if (!open) return null
  return createPortal(
    <div className="fixed inset-0 z-50">
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
          'absolute inset-y-0 right-0 flex w-full max-w-sm flex-col bg-bg shadow-pop transition-transform duration-300 ease-out',
          shown ? 'translate-x-0' : 'translate-x-full',
          className,
        )}
      >
        <div className="flex items-center justify-between border-b border-line px-6 py-5">
          <h2 className="text-lg font-bold">{title}</h2>
          <IconButton label="닫기" size="sm" onClick={onClose}>
            <CloseIcon />
          </IconButton>
        </div>
        <div className="flex-1 overflow-y-auto px-6 py-5">{children}</div>
      </div>
    </div>,
    document.body,
  )
}
