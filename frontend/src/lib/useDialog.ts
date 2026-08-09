import { useEffect, useRef, useState } from 'react'
import type { RefObject } from 'react'

const FOCUSABLE =
  'a[href], button:not([disabled]), input:not([disabled]), select:not([disabled]), textarea:not([disabled]), [tabindex]:not([tabindex="-1"])'

/** Modal/Drawer 공통 동작 — Esc 닫기 + 포커스 트랩 + 바디 스크롤 잠금 + 포커스 복원 */
export function useDialog(open: boolean, onClose: () => void, panelRef: RefObject<HTMLElement>) {
  // onClose는 매 렌더 새로 생길 수 있으므로 ref로 최신값만 참조 —
  // effect 의존성에서 빼서, 입력 중 재렌더마다 포커스가 다시 잡히는(=포커스 튕김) 문제를 막는다.
  const onCloseRef = useRef(onClose)
  onCloseRef.current = onClose

  useEffect(() => {
    if (!open) return
    const prev = document.activeElement as HTMLElement | null
    const panel = panelRef.current
    const focusables = panel?.querySelectorAll<HTMLElement>(FOCUSABLE)
    ;(focusables?.[0] ?? panel)?.focus()

    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') {
        e.stopPropagation()
        onCloseRef.current()
        return
      }
      if (e.key === 'Tab' && panel) {
        const els = [...panel.querySelectorAll<HTMLElement>(FOCUSABLE)].filter(
          (el) => el.offsetParent !== null,
        )
        if (els.length === 0) return
        const first = els[0]
        const last = els[els.length - 1]
        if (e.shiftKey && document.activeElement === first) {
          e.preventDefault()
          last.focus()
        } else if (!e.shiftKey && document.activeElement === last) {
          e.preventDefault()
          first.focus()
        }
      }
    }
    document.addEventListener('keydown', onKey)
    document.body.style.overflow = 'hidden'
    return () => {
      document.removeEventListener('keydown', onKey)
      document.body.style.overflow = ''
      prev?.focus()
    }
    // open/panelRef만 의존 — onClose 변경으로는 재실행하지 않는다
  }, [open, panelRef])
}

/** 마운트 직후 한 프레임 뒤 true — 진입 트랜지션용 */
export function useEnterTransition(open: boolean) {
  const [shown, setShown] = useState(false)
  useEffect(() => {
    if (!open) {
      setShown(false)
      return
    }
    const raf = requestAnimationFrame(() => setShown(true))
    return () => cancelAnimationFrame(raf)
  }, [open])
  return shown
}
