import type { ReactNode } from 'react'
import { Link } from 'react-router-dom'
import { useClockText, useR0KiTheme } from './R0KiShell'
import '../../styles/r0ki.css'

/* R0-Ki · AURA GLASS 인증 셸 — 로그인/회원가입/온보딩 전용.
   R0KiShell 과 달리 주 메뉴·알림이 없다(로그인 전이라 조회 권한이 없다).
   상단바는 브랜드 + 시계 + 야간모드만. 테마·시계 훅은 R0KiShell 것을 그대로 쓴다. */

export type R0KiAuthShellProps = {
  children: ReactNode
}

export function R0KiAuthShell({ children }: R0KiAuthShellProps) {
  const { theme, toggle } = useR0KiTheme()
  const clock = useClockText()

  return (
    <div className="r0ki r0ki-auth" data-theme={theme}>
      <div className="wrap">
        <div className="stage">
          <div className="scene" />

          <div className="au-top glass g2">
            <Link to="/" className="brand"><span className="core" /> R0-Ki</Link>
            <div className="sp" />
            <div className="clock num">
              {clock}<small>한국시간</small>
            </div>
            <button type="button" className="themebtn" onClick={toggle}>
              {theme === 'crystal' ? '야간 모드' : '주간 모드'}
            </button>
          </div>

          {children}
        </div>
      </div>
    </div>
  )
}
