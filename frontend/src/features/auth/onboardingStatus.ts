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
  /** 등록된 지도 — 대시보드 지도 조회에 그대로 쓴다 */
  mapId: string | number | null
  /** 이어서 진행할 단계 — 완료됐으면 null */
  nextPhase: OnboardingPhase | null
}

/**
 * 이어서 진행할 단계를 고른다.
 *
 * 스캔 단계는 "어느 로봇이 주행할지"를 알아야 시작할 수 있다. 로봇은 등록됐는데
 * 식별자를 못 구한 경우(로그인 응답에 없고 로봇 목록 조회도 실패)에 그대로 스캔으로
 * 보내면 [맵 파악하기] 버튼이 렌더되지 않아 빈 화면에 갇힌다 — 문지기가 /app 도
 * 막으므로 자력으로 못 빠져나온다. 그래서 로봇 등록부터 다시 밟게 한다.
 *
 * 지도까지 끝난 계정은 식별자를 몰라도 온보딩을 다시 시킬 이유가 없으므로 통과시킨다.
 */
function nextOnboardingPhase(
  robotRegistered: boolean,
  mapRegistered: boolean,
  robotId: string | number | null,
): OnboardingPhase | null {
  if (!robotRegistered) return 'robot'
  if (mapRegistered) return null
  if (robotId == null) return 'robot'
  return 'scan'
}

/**
 * 로그인 응답 + (필요 시) 로봇 목록으로 등록 상태를 만든다.
 *
 * 판정 근거는 로그인 응답의 hasRobot / hasMap 이다(백엔드 SigninResponse 필드명).
 * 값이 안 오는 경우:
 * - 로봇은 로봇 목록 조회로 보완한다.
 * - 지도는 "내 지도" 조회 API가 없어 보완할 수 없다. 이때는 등록된 것으로 보고
 *   흐름을 막지 않는다 — 여기서 미등록으로 단정하면 지도를 이미 등록한 사람까지
 *   맵 등록 화면에 갇힌다(실제로 필드명을 잘못 읽어 그 사고가 났었다).
 */
export async function readOnboardingStatus(
  data: SignInResponse['data'],
): Promise<OnboardingStatus> {
  let robotRegistered = data.hasRobot
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

  const mapId: string | number | null = data.mapId ?? null
  const mapRegistered = data.hasMap ?? true

  return {
    robotRegistered: Boolean(robotRegistered),
    mapRegistered,
    robotId,
    mapId,
    nextPhase: nextOnboardingPhase(Boolean(robotRegistered), mapRegistered, robotId),
  }
}
