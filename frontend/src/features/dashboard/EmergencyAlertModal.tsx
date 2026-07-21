import { Button, Modal } from '../../components/ui'
import { useClock } from '../landing/useClock'
import { useElapsed } from '../../lib/useElapsed'
import type { PatrolEvent } from '../../types/domain'

export type EmergencyAlertModalProps = {
  open: boolean
  event: PatrolEvent
  onClose: () => void
  /** [즉시 확인 →] — 긴급 이벤트 상세(1o)로 진입 */
  onConfirm: () => void
  /** [5분 후 다시 알림] */
  onSnooze: () => void
}

/** 긴급 알림 모달 (1c+) — 긴급상황 발생 시 대시보드 위에 표시 */
export function EmergencyAlertModal({ open, event, onClose, onConfirm, onSnooze }: EmergencyAlertModalProps) {
  const clock = useClock()
  // 목업: 탐지 12초 후 알림 도착 가정
  const elapsed = useElapsed(open, 12)

  return (
    <Modal open={open} onClose={onClose} className="max-w-lg ring-2 ring-danger">
      <div className="flex flex-col gap-4">
        {/* 헤더: [ 긴급 알림 ] + 현재 시각 */}
        <div className="flex items-center justify-between gap-3 pr-8">
          <span className="inline-flex items-center gap-2 font-mono text-xs font-bold tracking-widest text-danger">
            <span aria-hidden className="h-2 w-2 animate-pulse rounded-pill bg-danger" />
            [ 긴급 알림 ]
          </span>
          <span className="font-mono text-xs tabular text-muted">{clock}</span>
        </div>

        <h2 className="text-lg font-bold text-danger">
          ⚠ {event.type} 감지{event.subType ? ` — ${event.subType}` : ''}
        </h2>

        <div className="rounded-control bg-danger-soft px-4 py-3 text-sm leading-relaxed">
          <p>
            위치: <span className="font-semibold">{event.location}</span> · 탐지로봇{' '}
            <span className="font-mono tabular">{event.robotId}</span> (현장 대기중)
          </p>
          <p className="mt-1 text-muted">
            신뢰도 <span className="font-mono font-bold tabular text-fg">{event.confidence}%</span> · 경과{' '}
            <span className="font-mono font-bold tabular text-fg">{elapsed}</span>
          </p>
        </div>

        <div className="flex flex-wrap justify-end gap-2">
          <Button variant="outline" onClick={onSnooze}>
            5분 후 다시 알림
          </Button>
          <Button variant="dark" className="bg-danger" onClick={onConfirm}>
            즉시 확인 →
          </Button>
        </div>
      </div>
    </Modal>
  )
}
