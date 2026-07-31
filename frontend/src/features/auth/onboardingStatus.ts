import type { SignInResponse } from '../../api/contracts'
import { robotsApi, unwrapList } from '../../api/services'
import type { OnboardingPhase } from '../onboarding/useOnboardingProgress'

/* 로그인 직후 "이 계정이 온보딩을 끝냈는가"를 판정한다.
   계정만 만들고 이탈하면 로봇·지도가 없는 상태로 로그인하게 되는데,
   그대로 대시보드에 들여보내면 지도도 로봇도 없는 빈 관제 화면이 뜬다. */

export type OnboardingStatus = {
  robotRegistered: boolean
  mapRegistered: boolean
  robotId: string | number | null
  /** 이어서 진행할 단계 — 완료됐으면 null */
  nextPhase: OnboardingPhase | null
}

/**
 * 로그인 응답 + (필요 시) 로봇 목록으로 등록 상태를 만든다.
 *
 * 백엔드가 robotRegistered/mapRegistered 를 내려주는 것이 기본이고,
 * 아직 안 내려오는 동안에는 로봇 목록 조회로 로봇 등록 여부만 보완한다.
 * 지도는 조회 API가 없어 보완할 수 없으므로, 값이 없으면 "등록됨"으로 보고
 * 기존 사용자를 온보딩으로 잘못 되돌리지 않는다.
 */
export async function readOnboardingStatus(
  data: SignInResponse['data'],
): Promise<OnboardingStatus> {
  let robotRegistered = data.robotRegistered
  let robotId: string | number | null = data.robotId ?? null

  if (robotRegistered === undefined || robotId == null) {
    try {
      const robots = unwrapList(await robotsApi.list({ page: 0, size: 1 }))
      robotRegistered = robotRegistered ?? robots.length > 0
      robotId = robotId ?? robots[0]?.robotId ?? null
    } catch {
      // 조회 실패 시엔 등록된 것으로 보고 흐름을 막지 않는다 — 온보딩 재진입은 로그인마다 재판정된다
      robotRegistered = robotRegistered ?? true
    }
  }

  const mapRegistered = data.mapRegistered ?? true

  return {
    robotRegistered: Boolean(robotRegistered),
    mapRegistered,
    robotId,
    nextPhase: !robotRegistered ? 'robot' : !mapRegistered ? 'scan' : null,
  }
}
