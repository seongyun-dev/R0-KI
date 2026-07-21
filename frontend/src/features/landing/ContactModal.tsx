import { useEffect, useRef, useState, type FormEvent } from 'react'
import { BrandMark, CloseIcon } from '../../components/icons'
import { Button } from '../../components/ui'
import { useDialog } from '../../lib/useDialog'

export type ContactModalProps = {
  open: boolean
  onClose: () => void
}

/** 도입 문의 모달 — 폼 → 접수 완료 화면 (landing.html 포팅) */
export function ContactModal({ open, onClose }: ContactModalProps) {
  const panelRef = useRef<HTMLDivElement>(null)
  const [sending, setSending] = useState(false)
  const [success, setSuccess] = useState(false)
  useDialog(open, onClose, panelRef)

  // 닫힌 뒤(트랜지션 후) 폼 상태 초기화
  useEffect(() => {
    if (open) return
    const t = setTimeout(() => {
      setSending(false)
      setSuccess(false)
    }, 300)
    return () => clearTimeout(t)
  }, [open])

  const onSubmit = (e: FormEvent<HTMLFormElement>) => {
    e.preventDefault()
    setSending(true)
    setTimeout(() => setSuccess(true), 600)
  }

  return (
    <div className={`lmodal${open ? ' open' : ''}`} aria-hidden={!open} onClick={onClose}>
      <div
        ref={panelRef}
        className="lmodal__panel"
        role="dialog"
        aria-modal="true"
        aria-label="도입 문의"
        tabIndex={-1}
        onClick={(e) => e.stopPropagation()}
      >
        <button type="button" className="lmodal__close" onClick={onClose} aria-label="닫기" tabIndex={open ? 0 : -1}>
          <CloseIcon />
        </button>
        {!success ? (
          <div>
            <div className="lmodal__head">
              <span className="lmodal__eyebrow"><span className="dot" />도입 문의</span>
              <h2>단지에 맞는 견적을 받아보세요.</h2>
            </div>
            <form onSubmit={onSubmit}>
              <label className="field">
                <span className="cap">담당자 이름</span>
                <input type="text" name="name" required placeholder="이름을 입력하세요" disabled={!open} />
              </label>
              <label className="field">
                <span className="cap">단지명</span>
                <input type="text" name="site" required placeholder="예: 가온아파트" disabled={!open} />
              </label>
              <label className="field">
                <span className="cap">연락처</span>
                <input type="tel" name="phone" required placeholder="010-0000-0000" disabled={!open} />
              </label>
              <label className="field">
                <span className="cap">문의 내용</span>
                <textarea name="message" rows={3} placeholder="단지 규모, 도입 시기, 궁금한 점을 자유롭게 적어주세요." disabled={!open} />
              </label>
              <div className="lmodal__submit">
                <span className="lmodal__note">평일 기준 1영업일 내 연락드립니다.</span>
                <Button type="submit" variant="accent" withArrow="up-right" disabled={sending}>
                  {sending ? '보내는 중…' : '문의 보내기'}
                </Button>
              </div>
            </form>
          </div>
        ) : (
          <div className="lmodal__success">
            <div className="badge"><BrandMark className="mk" /></div>
            <h2>문의가 접수되었습니다</h2>
            <p>담당 상담원이 평일 기준 1영업일 내에 연락드리겠습니다. 감사합니다.</p>
            <Button variant="dark" onClick={onClose}>닫기</Button>
          </div>
        )}
      </div>
    </div>
  )
}
