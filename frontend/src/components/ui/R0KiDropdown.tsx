import { useEffect, useRef, useState } from 'react'

/* R0-Ki 커스텀 드롭다운 (시안 .dd)
   네이티브 select 는 OS 메뉴가 떠서 유리 톤이 깨지므로 직접 만든다.
   값이 선택되면 .set — 테두리·점으로 "필터 적용됨"을 표시. */

export type R0KiDropdownOption = { value: string; label: string }

export type R0KiDropdownProps = {
  /** 전체(미선택) 라벨 — value '' 일 때 표시 */
  allLabel: string
  options: R0KiDropdownOption[]
  value: string
  onChange: (value: string) => void
}

export function R0KiDropdown({ allLabel, options, value, onChange }: R0KiDropdownProps) {
  const [open, setOpen] = useState(false)
  const ref = useRef<HTMLDivElement>(null)

  // 바깥 클릭 · ESC 로 닫기
  useEffect(() => {
    if (!open) return
    const onDocClick = (e: MouseEvent) => {
      if (!ref.current?.contains(e.target as Node)) setOpen(false)
    }
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') setOpen(false)
    }
    document.addEventListener('click', onDocClick)
    document.addEventListener('keydown', onKey)
    return () => {
      document.removeEventListener('click', onDocClick)
      document.removeEventListener('keydown', onKey)
    }
  }, [open])

  const all: R0KiDropdownOption = { value: '', label: allLabel }
  const items = [all, ...options]
  const current = items.find((o) => o.value === value) ?? all

  return (
    <div className={`dd${open ? ' on' : ''}${value ? ' set' : ''}`} ref={ref}>
      <button
        type="button"
        className="dd-btn"
        aria-haspopup="listbox"
        aria-expanded={open}
        onClick={(e) => {
          e.stopPropagation()
          setOpen((v) => !v)
        }}
      >
        <span className="dd-lab">{current.label}</span>
        <svg viewBox="0 0 24 24"><path d="M6 9.5 12 15.5 18 9.5" /></svg>
      </button>
      {open && (
        <ul className="dd-menu" role="listbox">
          {items.map((o) => (
            <li
              key={o.value || '__all'}
              className="dd-opt"
              role="option"
              aria-selected={o.value === value}
              onClick={() => {
                onChange(o.value)
                setOpen(false)
              }}
            >
              <svg viewBox="0 0 24 24"><path d="M4 12.5 9.5 18 20 6.5" /></svg>
              {o.label}
            </li>
          ))}
        </ul>
      )}
    </div>
  )
}
