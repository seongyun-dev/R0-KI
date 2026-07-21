import { Link } from 'react-router-dom'
import { StatusBadge, toneOf } from '../../components/ui'
import { cn } from '../../lib/cn'
import type { PatrolPoint } from '../../types/domain'

const dotClass: Record<string, string> = {
  success: 'bg-success',
  info: 'bg-info',
  warning: 'bg-warning',
  danger: 'bg-danger',
  neutral: 'bg-subtle',
}

/** 순찰 타임라인 (1e) — 09:00 출발 / 09:12 불법주차 / … */
export function PatrolTimeline({ points, className }: { points: PatrolPoint[]; className?: string }) {
  return (
    <ol className={cn('flex flex-col', className)}>
      {points.map((p, i) => (
        <li key={`${p.time}-${i}`} className="relative flex gap-4 pb-6 last:pb-0">
          {/* 세로 라인 */}
          {i < points.length - 1 && (
            <span aria-hidden className="absolute left-[5px] top-4 h-full w-px bg-line" />
          )}
          <span aria-hidden className={cn('mt-1.5 h-[11px] w-[11px] flex-none rounded-pill', dotClass[toneOf(p.status)])} />
          <div className="flex min-w-0 flex-1 flex-wrap items-baseline gap-x-3 gap-y-1">
            <span className="font-mono text-sm font-bold tabular">{p.time}</span>
            <span className="text-sm font-semibold">{p.type}</span>
            <span className="text-sm text-muted">{p.location}</span>
            {p.note && <span className="w-full text-xs text-muted">{p.note}</span>}
          </div>
          {p.eventId ? (
            // 이상 지점 — 상태 변경은 이벤트 상세(1g)에서 관리
            <Link
              to={`/app/events/${p.eventId}`}
              aria-label={`${p.type} 이벤트 상세로 — 현재 상태 ${p.status}`}
              className="flex flex-none items-center gap-1 self-start transition-opacity hover:opacity-75"
            >
              <StatusBadge label={p.status} bracket />
              <span aria-hidden className="text-xs font-bold text-muted">→</span>
            </Link>
          ) : (
            <StatusBadge label={p.status} bracket className="flex-none self-start" />
          )}
        </li>
      ))}
    </ol>
  )
}
