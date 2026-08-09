import { useCallback, useEffect, useRef, useState } from 'react'
import { SiteHeader } from '../components/layout/SiteHeader'
import { SiteFooter } from '../components/layout/SiteFooter'
import { HowSection } from '../features/landing/HowSection'
import { PatrolStage } from '../features/landing/PatrolStage'
import { Loader } from '../features/landing/Loader'
import { NavMenu } from '../features/landing/NavMenu'
import { useClock } from '../features/landing/useClock'
import { useLenis } from '../features/landing/useLenis'
import { useReveal } from '../features/landing/useReveal'
import { usePrefersReducedMotion } from '../lib/usePrefersReducedMotion'
import '../features/landing/landing.css'

/** 랜딩 `/` (1p) — landing.html 프로토타입 이식 */
export default function Landing() {
  const reduceMotion = usePrefersReducedMotion()
  const [ready, setReady] = useState(reduceMotion)
  const [headerIn, setHeaderIn] = useState(false)
  const [menuOpen, setMenuOpen] = useState(false)
  const rootRef = useRef<HTMLDivElement>(null)
  const clock = useClock()

  const locked = !ready || menuOpen
  const lenisRef = useLenis(locked)
  useReveal(ready, rootRef)

  // 로더 종료 150ms 뒤 헤더 진입 (프로토타입 fireReady)
  useEffect(() => {
    if (!ready) return
    const t = setTimeout(() => setHeaderIn(true), 150)
    return () => clearTimeout(t)
  }, [ready])

  // adaptive rem grid — 랜딩에서만 html 폰트 스케일 (프로토타입 applyAdaptiveGrid)
  useEffect(() => {
    const html = document.documentElement
    html.classList.add('landing-grid')
    const FONT_BASE = 16
    const apply = () => {
      const w = window.innerWidth
      const widthReduction = ((1920 - w) / 1920) * 100
      const size = FONT_BASE - (FONT_BASE * (widthReduction * 0.6666)) / 100
      if (size > FONT_BASE) html.style.fontSize = `${size}px`
      else html.style.removeProperty('font-size')
    }
    apply()
    window.addEventListener('resize', apply)
    return () => {
      window.removeEventListener('resize', apply)
      html.classList.remove('landing-grid')
      html.style.removeProperty('font-size')
    }
  }, [])

  const scrollTo = useCallback(
    (id: string) => {
      const el = document.getElementById(id)
      if (!el) return
      lenisRef.current?.scrollTo(el, { offset: 0 })
    },
    [lenisRef],
  )

  return (
    <div ref={rootRef} className="landing">
      <a href="#main" className="skip">본문 바로가기</a>
      {!ready && <Loader onDone={() => setReady(true)} />}

      <SiteHeader
        shown={headerIn}
        clock={clock}
        onScrollTo={scrollTo}
        onMenuOpen={() => setMenuOpen(true)}
      />

      <main id="main">
        <PatrolStage ready={ready} />
        <HowSection />
      </main>

      <SiteFooter />

      <NavMenu
        open={menuOpen}
        clock={clock}
        onClose={() => setMenuOpen(false)}
        onScrollTo={scrollTo}
      />
    </div>
  )
}
