import type { ReactNode } from 'react'
import { cn } from '../../lib/cn'

export type FieldProps = {
  label: string
  htmlFor?: string
  required?: boolean
  /** 보조 설명 — 예: "4~20자 영문/숫자" */
  hint?: ReactNode
  /** 인라인 에러 — 예: "이미 사용중인 아이디입니다" (✕ 자동 표기) */
  error?: ReactNode
  className?: string
  children: ReactNode
}

/** label + control + hint/error 래퍼 (회원가입 등 폼 공통) */
export function Field({ label, htmlFor, required, hint, error, className, children }: FieldProps) {
  return (
    <div className={cn('flex flex-col gap-1.5', className)}>
      <label htmlFor={htmlFor} className="text-sm font-semibold">
        {label}
        {required && <span className="ml-0.5 text-accent" aria-hidden>*</span>}
      </label>
      {children}
      {error ? (
        <p role="alert" className="text-xs font-medium text-danger">✕ {error}</p>
      ) : (
        hint && <p className="text-xs text-muted">{hint}</p>
      )}
    </div>
  )
}
