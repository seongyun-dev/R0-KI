import { useEffect, useState, type FormEvent } from 'react'
import { Link, useLocation, useNavigate } from 'react-router-dom'
import { R0KiAuthShell } from '../components/layout/R0KiAuthShell'
import { ComplexSearchModal } from '../features/auth/ComplexSearchModal'
import { passwordStrength } from '../features/auth/passwordStrength'
import { useAuthStore } from '../features/auth/useAuthStore'
import { formatPhone } from '../lib/formatters'
import type { Complex } from '../types/domain'
import { authApi } from '../api/services'
import { env } from '../config/env'

// 목업 중복 데이터 — 서버 연동 시 API 교체
const TAKEN_IDS = ['admin', 'manager']
const TAKEN_NICKNAMES = ['관리자']

/** 온보딩(신규 단지)에서 기존 단지로 분기해 넘어올 때 이월되는 공통 필드 */
export type SignupPrefill = {
  username?: string
  password?: string
  name?: string
  phone?: string
  complex?: Complex
}

/** 회원가입 · 일반 회원 (1t) — 기존 단지 소속. R0Kiauth 시안 pExist */
export default function Signup() {
  const navigate = useNavigate()
  const location = useLocation()
  const login = useAuthStore((s) => s.login)
  const prefill = (location.state as { prefill?: SignupPrefill } | null)?.prefill

  const [loginId, setLoginId] = useState(prefill?.username ?? '')
  const [idCheck, setIdCheck] = useState<'idle' | 'ok' | 'taken'>('idle')
  const [pw, setPw] = useState(prefill?.password ?? '')
  const [pw2, setPw2] = useState('')
  const [name, setName] = useState(prefill?.name ?? '')
  const [nickname, setNickname] = useState('')
  const [nickCheck, setNickCheck] = useState<'idle' | 'ok' | 'taken'>('idle')
  const [phone, setPhone] = useState(prefill?.phone ?? '')
  const [complex, setComplex] = useState<Complex | null>(prefill?.complex ?? null)
  const [agree, setAgree] = useState(false)
  const [searchOpen, setSearchOpen] = useState(false)
  const [isPending, setPending] = useState(false)
  const [toast, setToast] = useState<string>()

  useEffect(() => {
    if (!toast) return
    const t = setTimeout(() => setToast(undefined), 2600)
    return () => clearTimeout(t)
  }, [toast])

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
      setToast('아파트단지를 선택해주세요')
      return
    }
    setPending(true)
    try {
      if (env.useMocks) {
        login(loginId)
      } else {
        const response = await authApi.signUp({
          username: loginId,
          password: pw,
          name: name,
          phoneNumber: phone,
          apartment: {
            name: complex.name,
            postalCode: complex.zipcode ?? '',
            address: complex.roadAddress,
          },
        })
        login(loginId, response.accessToken)
      }
      // 가입 완료 → 바로 대시보드
      navigate('/app', { replace: true })
    } catch (reason) {
      setToast(reason instanceof Error ? reason.message : '회원가입에 실패했습니다')
    } finally {
      setPending(false)
    }
  }

  return (
    <R0KiAuthShell>
      <div className="au-wrap">
        <form className="glass g2 au-card" onSubmit={onSubmit}>
          <h1 className="au-h">회원가입</h1>
          <p className="au-sub">기존 단지 소속 회원 가입입니다.</p>
          <div className="au-gap" />

          <div className={idCheck === 'taken' ? 'au-row bad' : 'au-row'}>
            <label className="au-lab" htmlFor="su-id">아이디<span className="req">*</span></label>
            <div className="au-pair">
              <input
                className={idCheck === 'taken' ? 'au-in bad' : 'au-in'}
                id="su-id"
                value={loginId}
                onChange={(e) => {
                  setLoginId(e.target.value)
                  setIdCheck('idle')
                }}
                placeholder="아이디 입력"
                pattern="[A-Za-z0-9]{4,20}"
                autoComplete="username"
                required
              />
              <button type="button" className="btn btn-s" onClick={checkId}>중복확인</button>
            </div>
            {idCheck === 'idle' && <p className="au-help">4~20자 영문/숫자</p>}
            {idCheck === 'taken' && <p className="au-err" role="alert">이미 사용중인 아이디입니다</p>}
            {idCheck === 'ok' && <p className="au-ok">✓ 사용 가능한 아이디입니다</p>}
          </div>

          <div className="au-row">
            <label className="au-lab" htmlFor="su-pw">비밀번호<span className="req">*</span></label>
            <input
              className="au-in"
              id="su-pw"
              type="password"
              value={pw}
              onChange={(e) => setPw(e.target.value)}
              placeholder="비밀번호 입력"
              autoComplete="new-password"
              minLength={8}
              required
            />
            {strength.level > 0 ? (
              <p className={strength.level === 3 ? 'au-ok' : 'au-help'}>
                {strength.dots} {strength.label}
              </p>
            ) : (
              <p className="au-help">8자 이상, 영문+숫자+특수문자 조합</p>
            )}
          </div>

          <div className={pwMismatch ? 'au-row bad' : 'au-row'}>
            <label className="au-lab" htmlFor="su-pw2">비밀번호 확인<span className="req">*</span></label>
            <input
              className={pwMismatch ? 'au-in bad' : 'au-in'}
              id="su-pw2"
              type="password"
              value={pw2}
              onChange={(e) => setPw2(e.target.value)}
              placeholder="비밀번호 다시 입력"
              autoComplete="new-password"
              required
            />
            {pwMismatch && <p className="au-err" role="alert">비밀번호가 일치하지 않습니다</p>}
          </div>

          <div className="au-row">
            <label className="au-lab" htmlFor="su-name">이름<span className="req">*</span></label>
            <input
              className="au-in"
              id="su-name"
              value={name}
              onChange={(e) => setName(e.target.value)}
              placeholder="이름 입력"
              required
            />
          </div>

          <div className={nickCheck === 'taken' ? 'au-row bad' : 'au-row'}>
            <label className="au-lab" htmlFor="su-nick">닉네임<span className="req">*</span></label>
            <div className="au-pair">
              <input
                className={nickCheck === 'taken' ? 'au-in bad' : 'au-in'}
                id="su-nick"
                value={nickname}
                onChange={(e) => {
                  setNickname(e.target.value)
                  setNickCheck('idle')
                }}
                placeholder="닉네임 입력"
                required
              />
              <button type="button" className="btn btn-s" onClick={checkNickname}>중복확인</button>
            </div>
            {nickCheck === 'taken' && <p className="au-err" role="alert">이미 사용중인 닉네임입니다</p>}
            {nickCheck === 'ok' && <p className="au-ok">✓ 사용 가능한 닉네임입니다</p>}
          </div>

          <div className="au-row">
            <label className="au-lab" htmlFor="su-phone">전화번호<span className="req">*</span></label>
            <input
              className="au-in num"
              id="su-phone"
              type="tel"
              value={phone}
              onChange={(e) => setPhone(formatPhone(e.target.value))}
              placeholder="010-1234-5678"
              required
            />
          </div>

          <div className="au-row">
            <label className="au-lab" htmlFor="su-complex">아파트단지<span className="req">*</span></label>
            <div className="au-pair">
              <span className="au-srch">
                <svg viewBox="0 0 24 24"><circle cx="11" cy="11" r="7" /><path d="m20 20-3.2-3.2" /></svg>
                <button type="button" id="su-complex" className="au-in" onClick={() => setSearchOpen(true)}>
                  {complex ? (
                    <span>{complex.name} · {complex.roadAddress}</span>
                  ) : (
                    <span className="ph">아파트단지를 검색해 선택하세요</span>
                  )}
                </button>
              </span>
              <button type="button" className="btn btn-s" onClick={() => setSearchOpen(true)}>검색</button>
            </div>
          </div>

          <label className="au-chk">
            <input type="checkbox" checked={agree} onChange={(e) => setAgree(e.target.checked)} required />
            <span className="bx"><svg viewBox="0 0 24 24"><path d="m5 13 4.5 4.5L19 7" /></svg></span>
            <span className="tx">이용약관 및 개인정보처리방침에 동의합니다</span>
          </label>

          <div className="au-act">
            <button type="submit" className="btn btn-p grow" disabled={isPending}>
              {isPending ? '가입 처리 중…' : '가입 완료'}
            </button>
          </div>
          <div className="au-foot">
            신규 아파트단지의 첫 관리자이신가요? <Link to="/signup/onboarding">최초 가입자 등록 →</Link>
            {' '}·{' '}
            <Link to="/login">로그인 →</Link>
          </div>
        </form>
      </div>

      <ComplexSearchModal
        open={searchOpen}
        onClose={() => setSearchOpen(false)}
        onSelect={(c) => {
          setComplex(c)
          setSearchOpen(false)
        }}
      />

      {/* 토스트 */}
      <div className={`toast${toast ? ' on' : ''}`} role="status" aria-live="polite">
        <svg viewBox="0 0 24 24"><path d="M4 12.5 9.5 18 20 6.5" /></svg>
        <span>{toast}</span>
      </div>
    </R0KiAuthShell>
  )
}
