import { useEffect } from 'react'
import { useNavigate } from 'react-router-dom'
import { BrandMark, CloseIcon } from '../../components/icons'

export type NavMenuProps = {
  open: boolean
  clock: string
  onClose: () => void
  onScrollTo: (id: string) => void
}

const items: { label: string; target?: string; to?: string }[] = [
  { label: '홈', target: 'home' },
  { label: '기능', target: 'features' },
  { label: '작동방식', target: 'how' },
  { label: '도입효과', target: 'impact' },
  { label: '로그인', to: '/login' },
  { label: '회원가입', to: '/signup/onboarding' },
]

/** 풀스크린 내비 메뉴 (landing.html 포팅) */
export function NavMenu({ open, clock, onClose, onScrollTo }: NavMenuProps) {
  const navigate = useNavigate()

  useEffect(() => {
    if (!open) return
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') onClose()
    }
    document.addEventListener('keydown', onKey)
    return () => document.removeEventListener('keydown', onKey)
  }, [open, onClose])

  const handle = (item: (typeof items)[number]) => {
    onClose()
    if (item.to) {
      navigate(item.to)
    } else if (item.target) {
      setTimeout(() => onScrollTo(item.target!), 60)
    }
  }

  return (
    <div className={`navmenu${open ? ' open' : ''}`} aria-hidden={!open}>
      <div className="shell navmenu__top">
        <div className="navmenu__brand">
          <BrandMark className="mk" />
          <span>AI 순찰 시스템</span>
        </div>
        <button type="button" className="nm-close" onClick={onClose}>
          <CloseIcon />
          닫기
        </button>
      </div>
      <nav className="shell navmenu__nav" aria-label="메뉴">
        <ul>
          {items.map((item, i) => (
            <li key={item.label}>
              <button
                type="button"
                className="nm-item"
                style={{ transitionDelay: `${i * 45 + 80}ms` }}
                onClick={() => handle(item)}
                tabIndex={open ? 0 : -1}
              >
                <span className="n font-mono tabular">0{i + 1}</span>
                <span className="l">{item.label}</span>
              </button>
            </li>
          ))}
        </ul>
      </nav>
      <div className="shell navmenu__bottom">
        <span>관제 시각 · <span className="font-mono tabular">{clock}</span></span>
        <button type="button" className="nm-start" onClick={() => { onClose(); navigate('/signup/onboarding') }} tabIndex={open ? 0 : -1}>
          회원가입하기 →
        </button>
      </div>
    </div>
  )
}
