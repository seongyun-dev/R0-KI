import { useEffect, useRef, useState } from 'react'
import { BrandMark } from '../icons'

/* 인증 화면 부팅 스크린 — 로그인·회원가입 진입 시 잠깐 덮었다가 위로 걷힌다.
   랜딩 로더(features/landing/Loader)와 같은 문법이지만 그쪽은 landing.css 에 묶여 있어
   인증 화면에서는 쓸 수 없다. 여기 스타일은 r0ki.css(.boot*) 가 담당한다.

   랜딩 로더보다 짧게 잡는다 — 첫 진입이 아니라 화면 전환이라 길면 방해가 된다. */

const FILL_MS = 700
const EXIT_MS = 520
const easeInOutCubic = (t: number) => (t < 0.5 ? 4 * t * t * t : 1 - Math.pow(-2 * t + 2, 3) / 2)
const pad3 = (n: number) => String(n).padStart(3, '0')

export type R0KiBootScreenProps = {
  /** 진행 바 아래 왼쪽 라벨 */
  label?: string
  /** 브랜드 아래 안내 문구 */
  tagline?: string
  /** 걷힘 애니메이션까지 끝난 뒤 */
  onDone: () => void
}

export function R0KiBootScreen({
  label = 'SYSTEM BOOT',
  tagline = '관제 시스템에 접속하고 있습니다.',
  onDone,
}: R0KiBootScreenProps) {
  const [progress, setProgress] = useState(0)
  const [exit, setExit] = useState(false)
  const doneRef = useRef(false)

  useEffect(() => {
    const start = performance.now()
    let raf = 0
    const tick = (now: number) => {
      const t = Math.min((now - start) / FILL_MS, 1)
      setProgress(Math.round(easeInOutCubic(t) * 100))
      if (t < 1) raf = requestAnimationFrame(tick)
      else setExit(true)
    }
    raf = requestAnimationFrame(tick)
    // 백그라운드 탭 등 rAF 가 멈추는 환경에서 부팅 화면에 갇히지 않도록
    const guard = window.setTimeout(() => {
      setProgress(100)
      setExit(true)
    }, FILL_MS + 900)
    return () => {
      cancelAnimationFrame(raf)
      window.clearTimeout(guard)
    }
  }, [])

  useEffect(() => {
    if (!exit) return
    const finish = () => {
      if (doneRef.current) return
      doneRef.current = true
      onDone()
    }
    const t = window.setTimeout(finish, EXIT_MS)
    return () => window.clearTimeout(t)
  }, [exit, onDone])

  return (
    <div className={`boot${exit ? ' exit' : ''}`} aria-hidden={exit}>
      <div className="boot__center">
        <div className="boot__brand">
          <BrandMark className="mk" />
          <span>AI 순찰 시스템</span>
        </div>
        <p className="boot__tag">{tagline}</p>
      </div>
      <div className="boot__progress" role="status" aria-live="polite">
        <div className="boot__track">
          <div className="boot__fill" style={{ width: `${progress}%` }} />
        </div>
        <div className="boot__row">
          <span>{label}</span>
          <span className="boot__count num">{pad3(progress)}</span>
        </div>
      </div>
    </div>
  )
}
