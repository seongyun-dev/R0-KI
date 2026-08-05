import { useEffect, useRef, useState } from 'react'
import { Link, useNavigate, useSearchParams } from 'react-router-dom'
import { R0KiAuthShell } from '../components/layout/R0KiAuthShell'
import { StepAccount } from '../features/onboarding/StepAccount'
import { StepMapScan } from '../features/onboarding/StepMapScan'
import { StepRobot } from '../features/onboarding/StepRobot'
import { StepZones } from '../features/onboarding/StepZones'
import { useRegisteredMap } from '../features/onboarding/useRegisteredMap'
import { SignupDoneModal } from '../features/onboarding/SignupDoneModal'
import {
  useOnboardingProgress,
  type OnboardingPhase,
} from '../features/onboarding/useOnboardingProgress'
import { authApi } from '../api/services'
import { useAuthStore } from '../features/auth/useAuthStore'

type Phase = 'account' | OnboardingPhase

// 화면별 제목/설명 (R0Kiauth 시안 문구)
const copy: Record<Phase, { title: string; description: string }> = {
  account: {
    title: '회원가입',
    description: '계정과 단지 정보를 함께 등록합니다. 이미 등록된 단지라면 소속 회원 가입으로 넘어갑니다.',
  },
  robot: {
    title: '첫 순찰 로봇 등록',
    description:
      '로봇 본체에 표기된 일련번호로 이 단지의 첫 로봇을 등록합니다. 등록된 로봇이 다음 단계에서 단지 맵을 직접 파악합니다.',
  },
  scan: {
    title: '게임패드로 단지 맵을 생성합니다',
    description:
      '[맵 파악하기]를 누른 뒤 deadman을 사용해 수동 주행하고, 현장에서 종료·저장하면 완성된 지도를 받습니다.',
  },
  zones: {
    title: '구역과 순찰 경로를 등록해주세요',
    description:
      '구역을 드래그해 저장한 뒤, 지도 위의 실제 경유·촬영·도착 지점을 순서대로 지정합니다.',
  },
}

// 스텝 인디케이터 [① 계정·단지][② 로봇 등록][③ 맵 등록]
const stepIndex: Record<Phase, number> = { account: 0, robot: 1, scan: 2, zones: 2 }
// 카드 폭 — 폼은 mid, 맵 편집은 map
const cardWidth: Record<Phase, string> = { account: 'w-mid', robot: 'w-mid', scan: 'w-map', zones: 'w-map' }

const STEP_LABELS = ['계정·단지', '로봇 등록', '맵 등록']

/** Stepper (.au-stp) — R0Kiauth 시안 신규 공용 컴포넌트 */
function AuthStepper({ current }: { current: number }) {
  return (
    <ol className="au-stp">
      {STEP_LABELS.map((label, i) => (
        <li key={label} className={i < current ? 'done' : i === current ? 'on' : ''}>
          <span className="st">
            <span className="n">
              {i < current ? <svg viewBox="0 0 24 24"><path d="m5 13 4.5 4.5L19 7" /></svg> : i + 1}
            </span>
            {label}
          </span>
          {i < STEP_LABELS.length - 1 && <span className="bar" />}
        </li>
      ))}
    </ol>
  )
}

/** 회원가입 · 최초 가입자 온보딩 (1u→1v→1w→1y) — R0Kiauth 시안 pNew→pRobot→pMap */
export default function SignupOnboarding() {
  const navigate = useNavigate()
  const [searchParams] = useSearchParams()
  const startsNewSignup = searchParams.get('new') === '1'
  const login = useAuthStore((state) => state.login)
  const currentLoginId = useAuthStore((state) => state.loginId)
  const onboardingOwner = useOnboardingProgress((state) => state.ownerLoginId)
  const storedPhase = useOnboardingProgress((state) => state.phase)
  const ownsStoredProgress =
    !startsNewSignup && currentLoginId != null && onboardingOwner === currentLoginId
  const storedRobotId = useOnboardingProgress((state) => state.robotId)
  const storedMapId = useOnboardingProgress((state) => state.mapId)
  const robotId = ownsStoredProgress ? storedRobotId : null
  const mapId = ownsStoredProgress ? storedMapId : null

  /* 단계에 필요한 값이 없으면 그 단계를 그릴 수 없다 — 스캔은 주행할 로봇을,
     구역 지정은 완성된 지도를 알아야 시작한다. 값이 갖춰진 가장 앞 단계로 되돌린다.
     그대로 두면 제목·설명만 뜨고 버튼이 하나도 없는 화면에 갇혀 자력으로 못 빠져나온다. */
  const resolvePhase = (): Phase => {
    if (!ownsStoredProgress || !storedPhase) return 'account'
    if (storedPhase === 'zones' && mapId == null) return robotId == null ? 'robot' : 'scan'
    if (storedPhase === 'scan' && robotId == null) return 'robot'
    return storedPhase
  }
  const phase = resolvePhase()
  const beginOnboarding = useOnboardingProgress((state) => state.begin)
  const moveToRobot = useOnboardingProgress((state) => state.moveToRobot)
  const moveToScan = useOnboardingProgress((state) => state.moveToScan)
  const moveToZones = useOnboardingProgress((state) => state.moveToZones)
  const resetOnboarding = useOnboardingProgress((state) => state.reset)
  const setRegisteredZones = useRegisteredMap((s) => s.setZones)
  const [isSubmitting, setIsSubmitting] = useState(false)
  const [errorMessage, setErrorMessage] = useState<string>()
  const setMapContext = useAuthStore((s) => s.setMapContext)
  const logout = useAuthStore((s) => s.logout)
  // 계정 등록을 마친 직후 안내 모달 — 닫으면 로봇 등록 단계가 그대로 드러난다
  const [signedUpId, setSignedUpId] = useState<string>()

  useEffect(() => {
    if (!startsNewSignup) return
    logout()
    resetOnboarding()
    navigate('/signup/onboarding', { replace: true })
  }, [logout, navigate, resetOnboarding, startsNewSignup])

  /* 모달을 열어둔 채 이 화면을 벗어나면(뒤로 가기 등) 로그아웃한다.
     계정은 만들어졌지만 로봇·지도가 없는 상태라, 세션을 남겨두면 로그인 화면에
     이미 로그인된 채로 서 있게 된다. 로그아웃해 두면 다음 로그인 때 서버 판정으로
     남은 단계부터 다시 이어진다. [로봇 등록하러 가기]를 누른 뒤에는 해당 없다. */
  const leavingBeforeContinueRef = useRef(false)
  leavingBeforeContinueRef.current = signedUpId != null
  useEffect(
    () => () => {
      if (!leavingBeforeContinueRef.current) return
      logout()
      resetOnboarding()
    },
    [logout, resetOnboarding],
  )

  return (
    <R0KiAuthShell bootTagline="관리자 계정 등록을 준비하고 있습니다.">
      <div className="au-wrap">
        <div className={`glass g2 au-card ${cardWidth[phase]}`}>
          <h1 className="au-h">{copy[phase].title}</h1>
          <p className="au-sub">{copy[phase].description}</p>
          <AuthStepper current={stepIndex[phase]} />
          <div className="au-gap" />

          {phase === 'account' && (
            <>
              <StepAccount
                isSubmitting={isSubmitting}
                errorMessage={errorMessage}
                onNext={async (data) => {
                  setIsSubmitting(true)
                  setErrorMessage(undefined)

                  try {
                    const response = await authApi.signUp(data)
                    login(data.username, data.name, response.accessToken)
                    // 이미 등록된 단지면 소속 회원으로 가입 완료 → 바로 대시보드
                    // (로봇·지도는 단지 관리자가 이미 등록해 둔 상태)
                    if (response.isNewApartment) {
                      /* 회원가입 API가 토큰을 발급하므로 이 시점에 이미 로그인 상태다.
                         온보딩 진행 상태를 모달을 닫은 뒤가 아니라 여기서 바로 세운다 —
                         모달이 떠 있는 동안 주소창으로 /app 에 들어가면 문지기(RequireAuth)가
                         진행 상태를 못 봐서, 로봇·지도 없는 빈 관제 화면이 그대로 열린다. */
                      beginOnboarding(data.username)
                      setSignedUpId(data.username)
                    } else {
                      resetOnboarding()
                      navigate('/app', { replace: true })
                    }
                  } catch (error) {
                    setErrorMessage(
                      error instanceof Error ? error.message : '회원가입에 실패했습니다.',
                    )
                  } finally {
                    setIsSubmitting(false)
                  }
                }}
              />
              {/* 일반 회원가입(/signup)은 front/dev 에서 제거됨 — 가입 경로는 온보딩 하나로 통일 */}
              <div className="au-foot">
                이미 계정이 있으신가요? <Link to="/login">로그인 →</Link>
              </div>
            </>
          )}
          {phase === 'robot' && (
            <StepRobot
              onPrev={() => navigate('/login')}
              onNext={({ robotId: registeredRobotId }) => {
                setMapContext({ robotId: registeredRobotId })
                /* 로봇 등록을 마치면 곧바로 맵 등록으로 넘어간다.
                   지도가 없으면 관제 화면이 비어 있어, 여기서 끊지 않고 이어서 받는다. */
                moveToScan(registeredRobotId)
              }}
            />
          )}
          {phase === 'scan' && robotId != null && (
            <StepMapScan
              robotId={robotId}
              onPrev={moveToRobot}
              onNext={(completedMapId) => {
                setMapContext({ mapId: completedMapId, robotId })
                moveToZones(completedMapId)
              }}
            />
          )}
          {phase === 'zones' && mapId != null && (
            <StepZones
              mapId={mapId}
              onPrev={() => {
                // 로봇을 모르면 스캔으로 돌아가도 시작할 수 없다 — 로봇 등록부터.
                // (조건만 걸어두면 버튼이 아무 반응 없이 먹통이 된다)
                if (robotId != null) moveToScan(robotId)
                else moveToRobot()
              }}
              onComplete={(zones) => {
                setRegisteredZones(zones) // 대시보드 지도에 반영
                resetOnboarding()
                // 가입 완료 → 바로 대시보드 (StepAccount 에서 이미 로그인됨)
                navigate('/app', { replace: true })
              }}
            />
          )}
        </div>
      </div>

      {/* 계정 등록 직후 안내 — 진행 상태는 위에서 이미 세웠으므로 여기서는 닫기만 한다.
          닫으면 바로 로봇 등록 단계다. 관제 화면으로 빠져나가는 길은 두지 않는다. */}
      <SignupDoneModal open={signedUpId != null} onContinue={() => setSignedUpId(undefined)} />
    </R0KiAuthShell>
  )
}
