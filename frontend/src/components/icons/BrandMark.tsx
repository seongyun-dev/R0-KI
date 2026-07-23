import type { SVGProps } from 'react'

/** 브랜드 마크 — landing.html #mk 심볼 (로봇 헬멧 + 렌즈) */
export function BrandMark(props: SVGProps<SVGSVGElement>) {
  return (
    <svg viewBox="0 0 48 48" width="1em" height="1em" aria-hidden="true" {...props}>
      <path
        fill="currentColor"
        d="M24 3c1.9 8.2 4.4 12.6 9.8 16.6l-4.5 3.4a12 12 0 0 0-10.6 0L14.2 19.6C19.6 15.6 22.1 11.2 24 3Z"
      />
      <circle cx="24" cy="30" r="9" fill="none" stroke="currentColor" strokeWidth="3.4" />
      <circle cx="24" cy="30" r="2.6" fill="currentColor" />
    </svg>
  )
}
