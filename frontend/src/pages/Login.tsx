import { useState } from 'react'
import { Link, useLocation, useNavigate } from 'react-router-dom'
import { R0KiAuthShell } from '../components/layout/R0KiAuthShell'
import { setAuthPersistence, useAuthStore } from '../features/auth/useAuthStore'
import { authApi, robotsApi } from '../api/services'
import { ApiError } from '../api/client'

/** 로그인 (1a) — R0Kiauth 시안 pLogin */
export default function Login() {
  const navigate = useNavigate()
  const location = useLocation()
  const login = useAuthStore((s) => s.login)
  const setMapContext = useAuthStore((s) => s.setMapContext)
  const [loginId, setLoginId] = useState('')
  const [password, setPassword] = useState('')
  // 목업 — 세션은 zustand persist 로 항상 유지된다. 서버 만료 정책 연동 시 값 사용
  const [remember, setRemember] = useState(true)
  const [isPending, setPending] = useState(false)
  const [error, setError] = useState<string>()
  // 가드에 막혀 왔다면 원래 가려던 곳으로 복귀
  const from = (location.state as { from?: string } | null)?.from ?? '/app'

  return (
    <R0KiAuthShell>
      <div className="au-wrap">
        <form
          className="glass g2 au-card"
          onSubmit={async (e) => {
            e.preventDefault()
            setPending(true)
            setError(undefined)
            try {
              const response = await authApi.signIn({
                username: loginId,
                password,
              })

              setAuthPersistence(remember)
              login(loginId, response.accessToken)

              navigate(from, { replace: true })
              void robotsApi
                .list({ page: 0, size: 1 })
                .then(({ content }) => {
                  setMapContext({ robotId: content[0]?.robotId ?? null })
                })
                .catch(() => undefined)
            } catch (reason) {
              setError(
                reason instanceof ApiError && reason.status === 401
                  ? '아이디 또는 비밀번호가 올바르지 않습니다.'
                  : reason instanceof Error
                    ? reason.message
                    : '로그인에 실패했습니다.',
              )
            } finally {
              setPending(false)
            }
          }}
        >
          <div className="au-brand">
            <span className="core" />
            <span className="tx">
              <span className="nm">R0-Ki</span>
              <span className="sl">AI 순찰 관제 시스템</span>
            </span>
          </div>
          <h1 className="au-h">로그인</h1>
          <p className="au-sub">등록된 관리자 계정으로 접속하세요.</p>
          <div className="au-gap" />

          <div className="au-row">
            <label className="au-lab" htmlFor="lgId">아이디<span className="req">*</span></label>
            <input
              className="au-in"
              id="lgId"
              name="loginId"
              value={loginId}
              onChange={(e) => setLoginId(e.target.value)}
              placeholder="아이디 입력"
              autoComplete="username"
              required
            />
          </div>
          <div className={error ? 'au-row bad' : 'au-row'}>
            <label className="au-lab" htmlFor="lgPw">비밀번호<span className="req">*</span></label>
            <input
              className={error ? 'au-in bad' : 'au-in'}
              id="lgPw"
              name="password"
              type="password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              placeholder="비밀번호 입력"
              autoComplete="current-password"
              required
            />
            {error && <p className="au-err" role="alert">{error}</p>}
          </div>

          <label className="au-chk">
            <input type="checkbox" checked={remember} onChange={(e) => setRemember(e.target.checked)} />
            <span className="bx"><svg viewBox="0 0 24 24"><path d="m5 13 4.5 4.5L19 7" /></svg></span>
            <span className="tx">로그인 상태 유지</span>
          </label>

          <div className="au-act">
            <button type="submit" className="btn btn-p grow" disabled={isPending}>
              {isPending ? '로그인 중…' : '로그인'}
            </button>
          </div>
          <div className="au-foot">
            아직 계정이 없으신가요? <Link to="/signup/onboarding">회원가입 →</Link>
          </div>
        </form>
      </div>
    </R0KiAuthShell>
  )
}
