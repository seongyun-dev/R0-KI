import { useEffect, useRef } from 'react'

/* 대시보드 알림 공통 인프라 — 긴급 알림(useEmergencyAlert)과 순찰 완료(usePatrolComplete)가
   같은 구조를 쓰고 있어 한 곳으로 모았다. 폴링 정책(가시성·백오프)과 확인 기록 보관을
   여기서만 관리하면, 나중에 SSE 로 바꿀 때도 이 파일만 손보면 된다. */

const SEEN_LIMIT = 200

/**
 * "이미 확인한 알림" 기록 — localStorage.
 *
 * 상한을 둔다. 관제 화면은 하루에도 수십~수백 건이 쌓이는데 무제한으로 append 하면
 * 몇 달 뒤 파싱·순회 비용이 커지고 결국 5MB 쿼터에 걸린다.
 * 오래된 기록이 밀려나도 문제없다 — 그만큼 지난 알림은 목록에서도 사라진다.
 */
export function createSeenStore(key: string, limit = SEEN_LIMIT) {
  const read = (): string[] => {
    try {
      const raw = JSON.parse(localStorage.getItem(key) ?? '[]')
      return Array.isArray(raw) ? raw.filter((v): v is string => typeof v === 'string') : []
    } catch {
      return []
    }
  }

  return {
    isSeen: (id: string) => read().includes(id),
    markSeen: (id: string) => {
      const seen = read()
      if (seen.includes(id)) return
      try {
        // 최근 limit 건만 유지 — 앞(오래된 것)부터 밀어낸다
        localStorage.setItem(key, JSON.stringify([...seen, id].slice(-limit)))
      } catch {
        // 쿼터 초과 등 — 기록을 못 남겨도 알림 자체는 동작해야 한다
      }
    },
  }
}

const BASE_INTERVAL_MS = 5000
const MAX_INTERVAL_MS = 60000

export type PolledFeedOptions<TItem, TDomain> = {
  /** 목록 조회 — 항상 배열을 돌려줘야 한다(호출측에서 unwrapList) */
  fetchItems: () => Promise<TItem[]>
  /** 중복 판별용 키 */
  getId: (item: TItem) => string
  /** 콜백에 넘길 도메인 형태로 변환 */
  toDomain: (item: TItem) => TDomain
  /** 새로 생긴 항목이 있을 때 (가장 최근 1건) */
  onNew: (value: TDomain) => void
  /** 폴링 주기 (기본 5초) */
  intervalMs?: number
  /** 개발 모드 경고에 붙일 이름 */
  label: string
  /** false 면 폴링하지 않는다 (목업 모드 등) */
  enabled?: boolean
}

/**
 * 목록을 주기 조회해 "새로 생긴 것"만 콜백한다.
 *
 * - 최초 조회분은 기존 항목으로 간주한다(진입하자마자 과거 알림이 쏟아지지 않게).
 * - 탭이 백그라운드면 쉰다. 관제 화면은 종일 띄워두는 성격이라 그대로 두면
 *   보지도 않는 화면이 분당 수십 건을 계속 던진다. 복귀 시 즉시 한 번 조회한다.
 * - 실패하면 주기를 2배씩 늘린다(최대 60초). 서버가 죽었을 때 5초마다 두드리지 않기 위해서다.
 *   성공하면 기본 주기로 돌아온다.
 */
export function usePolledFeed<TItem, TDomain>({
  fetchItems,
  getId,
  toDomain,
  onNew,
  intervalMs = BASE_INTERVAL_MS,
  label,
  enabled = true,
}: PolledFeedOptions<TItem, TDomain>) {
  // 콜백·조회 함수는 매 렌더 새로 만들어져도 폴링이 재시작되지 않도록 ref 로 고정한다
  const onNewRef = useRef(onNew)
  onNewRef.current = onNew
  const fetchRef = useRef(fetchItems)
  fetchRef.current = fetchItems
  const getIdRef = useRef(getId)
  getIdRef.current = getId
  const toDomainRef = useRef(toDomain)
  toDomainRef.current = toDomain

  useEffect(() => {
    if (!enabled) return

    let disposed = false
    let initialized = false
    let delay = intervalMs
    let timer: number | undefined
    const knownIds = new Set<string>()

    const schedule = () => {
      if (disposed) return
      timer = window.setTimeout(run, delay)
    }

    const run = async () => {
      if (disposed) return
      // 백그라운드 탭이면 조회를 건너뛰고 다음 주기로 — 복귀는 visibilitychange 가 깨운다
      if (document.visibilityState === 'hidden') {
        schedule()
        return
      }

      try {
        const items = await fetchRef.current()
        if (disposed) return

        if (initialized) {
          const added = items.filter((item) => !knownIds.has(getIdRef.current(item)))
          if (added.length > 0) onNewRef.current(toDomainRef.current(added[0]))
        }
        items.forEach((item) => knownIds.add(getIdRef.current(item)))
        initialized = true
        delay = intervalMs
      } catch (reason) {
        if (disposed) return
        delay = Math.min(delay * 2, MAX_INTERVAL_MS)
        // 조용히 삼키면 알림이 계속 안 뜨는 상태를 눈치챌 수 없어 개발 중엔 남긴다
        if (import.meta.env.DEV) {
          console.warn(`[${label}] 조회 실패 — ${delay}ms 뒤 재시도`, reason)
        }
      }
      schedule()
    }

    const onVisible = () => {
      if (document.visibilityState !== 'visible' || disposed) return
      window.clearTimeout(timer)
      delay = intervalMs
      void run()
    }

    void run()
    document.addEventListener('visibilitychange', onVisible)
    return () => {
      disposed = true
      window.clearTimeout(timer)
      document.removeEventListener('visibilitychange', onVisible)
    }
  }, [enabled, intervalMs, label])
}
