import { useState } from 'react'
import { Link, useLocation, useNavigate } from 'react-router-dom'
import { Button, Field, Input } from '../components/ui'
import { SiteHeader } from '../components/layout/SiteHeader'
import { AuthLayout } from '../features/auth/AuthLayout'
import { useAuthStore } from '../features/auth/useAuthStore'
import { useClock } from '../features/landing/useClock'
import { authApi } from '../api/services'
import { env } from '../config/env'

/** 로그인 (1a) */
export default function Login() {
  const navigate = useNavigate()
  const location = useLocation()
  const login = useAuthStore((s) => s.login)
  const clock = useClock()
  const [loginId, setLoginId] = useState('')
  const [password, setPassword] = useState('')
  const [isPending, setPending] = useState(false)
  const [error, setError] = useState<string>()
  // 가드에 막혀 왔다면 원래 가려던 곳으로 복귀
  const from = (location.state as { from?: string } | null)?.from ?? '/app'

  return (
    <AuthLayout
      title="AI 순찰 로봇 관리자 로그인"
      header={<SiteHeader plain clock={clock} />}
    >
      <form
        className="flex flex-col gap-5"
        onSubmit={async (e) => {
          e.preventDefault()
          setPending(true)
          setError(undefined)
          try {
            if (env.useMocks) {
              login(loginId)
            } else {
              const response = await authApi.signIn({ username: loginId, password })
              login(loginId, response.accessToken)
            }
            navigate(from, { replace: true })
          } catch (reason) {
            setError(reason instanceof Error ? reason.message : '로그인에 실패했습니다')
          } finally {
            setPending(false)
          }
        }}
      >
        <Field label="아이디" htmlFor="login-id" error={error}>
          <Input
            id="login-id"
            name="loginId"
            value={loginId}
            onChange={(e) => setLoginId(e.target.value)}
            placeholder="아이디 입력"
            autoComplete="username"
            required
          />
        </Field>
        <Field label="비밀번호" htmlFor="login-pw">
          <Input
            id="login-pw"
            name="password"
            type="password"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            placeholder="비밀번호 입력"
            autoComplete="current-password"
            required
          />
        </Field>
        <Button type="submit" variant="accent" className="mt-2 w-full" loading={isPending}>
          로그인
        </Button>
      </form>
      <p className="mt-6 text-center text-sm text-muted">
        계정이 없으신가요?{' '}
        <Link to="/signup/onboarding" className="font-semibold text-fg underline-offset-4 hover:underline">
          회원가입 →
        </Link>
      </p>
    </AuthLayout>
  )
}
