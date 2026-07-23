import { useEffect, useRef } from 'react'
import Lenis from 'lenis'

/**
 * 랜딩 부드러운 스크롤. locked=true면 스크롤 정지(로더/메뉴/모달).
 * 반환된 ref로 scrollTo 사용.
 */
export function useLenis(locked: boolean) {
  const lenisRef = useRef<Lenis | null>(null)

  useEffect(() => {
    const lenis = new Lenis({ smoothWheel: true })
    lenisRef.current = lenis
    let raf = 0
    const loop = (t: number) => {
      lenis.raf(t)
      raf = requestAnimationFrame(loop)
    }
    raf = requestAnimationFrame(loop)
    return () => {
      cancelAnimationFrame(raf)
      lenis.destroy()
      lenisRef.current = null
    }
  }, [])

  useEffect(() => {
    const lenis = lenisRef.current
    const html = document.documentElement
    if (locked) {
      lenis?.stop()
      html.style.overflow = 'hidden'
      html.style.height = '100%'
    } else {
      lenis?.start()
      html.style.removeProperty('overflow')
      html.style.removeProperty('height')
    }
    return () => {
      html.style.removeProperty('overflow')
      html.style.removeProperty('height')
    }
  }, [locked])

  return lenisRef
}
