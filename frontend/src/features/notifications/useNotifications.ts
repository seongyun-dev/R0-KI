import { notificationsApi, unwrapList } from '../../api/services'
import {
  notificationDetailToDomain,
  notificationListItemToDomain,
} from '../../api/mappers'
import { useApiQuery } from '../../lib/useApiQuery'
import type { NotificationRecord } from '../../types/domain'

/* 알림 기록 — 목록 조회 / 상세 조회. API 연결(services.notificationsApi)은 그대로 쓴다.

/** 최신순 — 발송 시각 내림차순. 미발송(sentAt 없음)은 뒤로, 동률은 알림 ID 내림차순. */
function byLatest(a: NotificationRecord, b: NotificationRecord) {
  const at = a.sentAt ? Date.parse(a.sentAt) : Number.NaN
  const bt = b.sentAt ? Date.parse(b.sentAt) : Number.NaN
  const aOk = Number.isFinite(at)
  const bOk = Number.isFinite(bt)
  if (aOk && bOk && at !== bt) return bt - at
  if (aOk !== bOk) return aOk ? -1 : 1
  return b.backendId - a.backendId
}

/** 알림 목록 (GET /api/notifications) — 상태 필터 없이 전체를 최신순으로 */
export function useNotifications() {
  return useApiQuery(
    async () => {
      const response = await notificationsApi.list()
      // ?? [] 만으로는 배열 응답에서 조용히 빈 목록이 된다 — unwrapList 로 형태를 흡수한다.
      return unwrapList(response).map(notificationListItemToDomain).sort(byLatest)
    },
    [],
    { delayMs: 0 },
  )
}

/** 알림 상세 (GET /api/notifications/{notificationId}) */
export function useNotification(id: string | undefined) {
  const notificationId = Number(id)
  const valid = Boolean(id) && Number.isFinite(notificationId)
  return useApiQuery(
    async () => {
      if (!valid) return undefined
      return notificationDetailToDomain(await notificationsApi.detail(notificationId))
    },
    [id],
    { enabled: valid, delayMs: 0 },
  )
}
