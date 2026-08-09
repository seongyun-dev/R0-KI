import { useEffect, useRef, useState } from 'react'
import { Button } from '../ui/Button'
import { SlideToStart } from '../../features/landing/SlideToStart'

/**
 * 랜딩 푸터 — 지금은 시작 CTA 하나만 둔다.
 * [순찰 시작하기]를 누르면 회원가입 / 로그인 두 갈래로 펼쳐진다.
 * (링크 컬럼·카피라이트는 걷어낸 상태 — 실제 페이지가 생기면 다시 넣는다)
 */
export function SiteFooter() {
  const [open, setOpen] = useState(false)
  const choicesRef = useRef<HTMLDivElement>(null)

  // 펼친 직후 첫 선택지로 초점을 옮겨 키보드로도 이어서 고를 수 있게
  // (Button이 ref를 넘기지 않아 컨테이너에서 첫 요소를 찾는다)
  useEffect(() => {
    if (!open) return
    choicesRef.current?.querySelector<HTMLElement>('a, button')?.focus()
  }, [open])

  return (
    <footer className="landing-footer">
      <div className="shell footer-start">
        {open ? (
          <div ref={choicesRef} className="footer-cta__choices" role="group" aria-label="시작 방법 선택">
            {/* 밝은 배경이라 두 번째 버튼은 outline이 또렷하다 */}
            <Button variant="accent" size="lg" withArrow="up-right" to="/signup/onboarding?new=1">
              회원가입하기
            </Button>
            <Button variant="outline" size="lg" to="/login">
              로그인하기
            </Button>
          </div>
        ) : (
          <SlideToStart label="밀어서 순찰 시작" onComplete={() => setOpen(true)} />
        )}
      </div>
    </footer>
  )
}
