import { useEffect, type ReactNode } from 'react'
import { createPortal } from 'react-dom'

export type R0KiModalProps = {
  open: boolean
  onClose: () => void
  title: string
  children: ReactNode
}

/* r0ki 공용 모달 — .stage 직계 자식으로 포탈한다.
   유리 카드(.glass)의 backdrop-filter 가 position:fixed 의 컨테이닝 블록이 되므로
   카드 안에서 그대로 렌더하면 모달이 카드 좌표계에 갇힌다. .stage 직계는
   .stage>* z-index 규칙에서 .modalwrap 로 제외되어 화면 전체에 뜬다. */
export function R0KiModal({ open, onClose, title, children }: R0KiModalProps) {
  useEffect(() => {
    if (!open) return
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') onClose()
    }
    document.addEventListener('keydown', onKey)
    return () => document.removeEventListener('keydown', onKey)
  }, [open, onClose])

  if (!open) return null

  const node = (
    <div className="modalwrap">
      <div className="backdrop" onClick={onClose} />
      <div className="modal g3 glass" role="dialog" aria-modal="true" aria-label={title}>
        <div className="mdhead">
          <h2>{title}</h2>
          <button type="button" className="mdx" onClick={onClose} aria-label="닫기">
            <svg viewBox="0 0 24 24"><path d="M6 6l12 12M18 6L6 18" /></svg>
          </button>
        </div>
        {children}
      </div>
    </div>
  )
  // 모달은 열린 뒤에만 렌더되므로 이 시점엔 셸(.stage)이 항상 마운트돼 있다
  const host = document.querySelector('.r0ki .stage')
  return host ? createPortal(node, host) : node
}
