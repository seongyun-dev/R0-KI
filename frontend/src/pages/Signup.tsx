import { useState, type FormEvent } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { SearchIcon } from '../components/icons'
import { Button, Checkbox, Field, Input, useToast } from '../components/ui'
import { SiteHeader } from '../components/layout/SiteHeader'
import { AuthLayout } from '../features/auth/AuthLayout'
import { useClock } from '../features/landing/useClock'
import { ComplexSearchModal } from '../features/auth/ComplexSearchModal'
import { passwordStrength } from '../features/auth/passwordStrength'
import { cn } from '../lib/cn'
import { formatPhone } from '../lib/formatters'
import type { Complex } from '../types/domain'
import { authApi } from '../api/services'
import { env } from '../config/env'

// 목업 중복 데이터 — 서버 연동 시 API 교체
const TAKEN_IDS = ['admin', 'manager']
const TAKEN_NICKNAMES = ['관리자']

const strengthColor = ['', 'text-danger', 'text-warning', 'text-success']

/** 회원가입 · 일반 회원 (1t) — 기존 단지 소속 */
export default function Signup() {
  const navigate = useNavigate()
  const toast = useToast()
  const clock = useClock()

  const [loginId, setLoginId] = useState('')
  const [idCheck, setIdCheck] = useState<'idle' | 'ok' | 'taken'>('idle')
  const [pw, setPw] = useState('')
  const [pw2, setPw2] = useState('')
  const [name, setName] = useState('')
  const [nickname, setNickname] = useState('')
  const [nickCheck, setNickCheck] = useState<'idle' | 'ok' | 'taken'>('idle')
  const [phone, setPhone] = useState('')
  const [complex, setComplex] = useState<Complex | null>(null)
  const [agree, setAgree] = useState(false)
  const [searchOpen, setSearchOpen] = useState(false)
  const [isPending, setPending] = useState(false)

  const strength = passwordStrength(pw)
  const pwMismatch = pw2.length > 0 && pw !== pw2

  const checkId = () => {
    if (!loginId) return
    setIdCheck(TAKEN_IDS.includes(loginId.toLowerCase()) ? 'taken' : 'ok')
  }
  const checkNickname = () => {
    if (!nickname) return
    setNickCheck(TAKEN_NICKNAMES.includes(nickname) ? 'taken' : 'ok')
  }

  const onSubmit = async (e: FormEvent<HTMLFormElement>) => {
    e.preventDefault()
    if (pwMismatch) return
    if (!complex) {
      toast('아파트단지를 선택해주세요')
      return
    }
    setPending(true)
    try {
      if (!env.useMocks) {
        await authApi.signUp({
          username: loginId,
          password: pw,
          name: name,
          phoneNumber: phone,
          apartment: {
            name: complex.name,
            postalCode: complex.zipcode ?? '',
            address: complex.roadAddress,
          }
          })
      }
      toast('✓ 가입이 완료되었습니다')
      navigate('/login')
    } catch (reason) {
      toast(reason instanceof Error ? reason.message : '회원가입에 실패했습니다')
    } finally {
      setPending(false)
    }
  }

  return (
    <AuthLayout
      title="회원가입"
      description="기존 단지 소속 회원 가입입니다."
      header={<SiteHeader plain clock={clock} />}
    >
      <form className="flex flex-col gap-5" onSubmit={onSubmit} noValidate={false}>
        <Field
          label="아이디"
          htmlFor="su-id"
          required
          hint={idCheck === 'ok' ? undefined : '4~20자 영문/숫자'}
          error={idCheck === 'taken' ? '이미 사용중인 아이디입니다' : undefined}
        >
          <div className="flex gap-2">
            <Input
              id="su-id"
              value={loginId}
              onChange={(e) => {
                setLoginId(e.target.value)
                setIdCheck('idle')
              }}
              placeholder="아이디 입력"
              pattern="[A-Za-z0-9]{4,20}"
              invalid={idCheck === 'taken'}
              required
            />
            <Button variant="outline" className="flex-none" onClick={checkId}>
              중복확인
            </Button>
          </div>
          {idCheck === 'ok' && <p className="text-xs font-medium text-success">✓ 사용 가능한 아이디입니다</p>}
        </Field>

        <Field label="비밀번호" htmlFor="su-pw" required hint="8자 이상, 영문+숫자+특수문자 조합">
          <Input
            id="su-pw"
            type="password"
            value={pw}
            onChange={(e) => setPw(e.target.value)}
            placeholder="비밀번호 입력"
            autoComplete="new-password"
            minLength={8}
            required
          />
          {strength.level > 0 && (
            <p className={cn('text-xs font-semibold', strengthColor[strength.level])}>
              {strength.dots} {strength.label}
            </p>
          )}
        </Field>

        <Field
          label="비밀번호 확인"
          htmlFor="su-pw2"
          required
          error={pwMismatch ? '비밀번호가 일치하지 않습니다' : undefined}
        >
          <Input
            id="su-pw2"
            type="password"
            value={pw2}
            onChange={(e) => setPw2(e.target.value)}
            placeholder="비밀번호 다시 입력"
            autoComplete="new-password"
            invalid={pwMismatch}
            required
          />
        </Field>

        <Field label="이름" htmlFor="su-name" required>
          <Input id="su-name" value={name} onChange={(e) => setName(e.target.value)} placeholder="이름 입력" required />
        </Field>

        <Field
          label="닉네임"
          htmlFor="su-nick"
          required
          error={nickCheck === 'taken' ? '이미 사용중인 닉네임입니다' : undefined}
        >
          <div className="flex gap-2">
            <Input
              id="su-nick"
              value={nickname}
              onChange={(e) => {
                setNickname(e.target.value)
                setNickCheck('idle')
              }}
              placeholder="닉네임 입력"
              invalid={nickCheck === 'taken'}
              required
            />
            <Button variant="outline" className="flex-none" onClick={checkNickname}>
              중복확인
            </Button>
          </div>
          {nickCheck === 'ok' && <p className="text-xs font-medium text-success">✓ 사용 가능한 닉네임입니다</p>}
        </Field>

        <Field label="전화번호" htmlFor="su-phone" required>
          <Input
            id="su-phone"
            type="tel"
            value={phone}
            onChange={(e) => setPhone(formatPhone(e.target.value))}
            placeholder="010-1234-5678"
            className="font-mono tabular"
            required
          />
        </Field>

        <Field label="아파트단지" htmlFor="su-complex" required>
          <div className="flex gap-2">
            <button
              type="button"
              id="su-complex"
              onClick={() => setSearchOpen(true)}
              className={cn(
                'flex w-full items-center gap-2 rounded-control bg-bg px-4 py-3 text-left text-sm ring-1 ring-line',
                complex ? 'text-fg' : 'text-subtle',
              )}
            >
              <SearchIcon className="flex-none text-muted" />
              {complex ? `${complex.name} · ${complex.roadAddress}` : '아파트단지를 검색해 선택하세요'}
            </button>
            <Button variant="outline" className="flex-none" onClick={() => setSearchOpen(true)}>
              검색
            </Button>
          </div>
        </Field>

        <Checkbox
          label="이용약관 및 개인정보처리방침에 동의합니다"
          checked={agree}
          onChange={(e) => setAgree(e.target.checked)}
          required
        />

        <Button type="submit" variant="accent" className="mt-2 w-full" loading={isPending}>
          가입 완료
        </Button>
      </form>

      <p className="mt-6 border-t border-line pt-5 text-center text-sm text-muted">
        신규 아파트단지의 첫 관리자이신가요?{' '}
        <Link to="/signup/onboarding" className="font-semibold text-fg underline-offset-4 hover:underline">
          최초 가입자 등록 →
        </Link>
      </p>

      <ComplexSearchModal
        open={searchOpen}
        onClose={() => setSearchOpen(false)}
        onSelect={(c) => {
          setComplex(c)
          setSearchOpen(false)
        }}
      />
    </AuthLayout>
  )
}
