import { notifications } from '../../mocks'
import { notificationsApi } from '../../api/services'
import {
  notificationDetailToDomain,
  notificationListItemToDomain,
} from '../../api/mappers'
import { env } from '../../config/env'
import { useApiQuery } from '../../lib/useApiQuery'
import type { NotificationRecord } from '../../types/domain'

/* 알림 기록 — 목록 조회 / 상세 조회. API 연결(services.notificationsApi)은 그대로 쓴다.
   VITE_USE_MOCKS=true 면 목업으로 화면만 확인한다(이벤트 상세와 같은 방식). */

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
      if (env.useMocks) return [...notifications].sort(byLatest)
      const response = await notificationsApi.list()
      return (response.content ?? []).map(notificationListItemToDomain).sort(byLatest)
    },
    [],
    { delayMs: env.useMocks ? 350 : 0 },
  )
}

/** 알림 상세 (GET /api/notifications/{notificationId}) */
export function useNotification(id: string | undefined) {
  const notificationId = Number(id)
  const valid = Boolean(id) && Number.isFinite(notificationId)
  return useApiQuery(
    async () => {
      if (!valid) return undefined
      if (env.useMocks) return notifications.find((n) => n.id === id)
      return notificationDetailToDomain(await notificationsApi.detail(notificationId))
    },
    [id],
    { enabled: valid, delayMs: env.useMocks ? 350 : 0 },
  )
}
