import {
  useEffect,
  useMemo,
  useRef,
  useState,
  type FormEvent,
} from 'react'
import { createPortal } from 'react-dom'

import {
  useEvent,
  useEvidenceImage,
  useUpdateEventStatus,
} from '../../features/events/useEvents'

import { useElapsed } from '../../lib/useElapsed'
import type { ProcessingStatus } from '../../types/domain'

type EventDetailModalProps = {
  eventId: string | null
  onClose: () => void
  onStatusChanged?: (
    eventId: string,
    status: ProcessingStatus,
  ) => void
}

const PROC_STATUSES: ProcessingStatus[] = [
  '탐지',
  '처리중',
  '처리완료',
]

const PROC_STATUS_ATTR: Record<ProcessingStatus, string> = {
  탐지: 'detected',
  처리중: 'processing',
  처리완료: 'completed',
}

const RISK_DOT: Record<string, string> = {
  보통: 'var(--detect)',
  낮음: 'var(--offline)',
}

const EVIDENCE_POLL_INTERVAL_MS = 5000
const EVIDENCE_POLL_MAX_TRIES = 12

export function EventDetailModal({
  eventId,
  onClose,
  onStatusChanged,
}: EventDetailModalProps) {
  const {
    data: event,
    isLoading,
    error,
    refetch,
  } = useEvent(eventId ?? undefined)

  const {
    data: evidenceImageUrl,
    isLoading: isEvidenceLoading,
    error: evidenceError,
    refetch: refetchEvidence,
  } = useEvidenceImage(event?.evidenceImageUrl)

  const updateStatus = useUpdateEventStatus()

  const [proc, setProc] =
    useState<ProcessingStatus>('탐지')

  const [memo, setMemo] = useState<string>()
  const [processedAt, setProcessedAt] =
    useState<string>()

  const [memoModalOpen, setMemoModalOpen] =
    useState(false)

  const [memoInput, setMemoInput] = useState('')
  const [toast, setToast] = useState<string>()

  /* 서버 이벤트 상태 반영 */
  useEffect(() => {
    if (!event) return

    setProc(
      event.processingStatus ??
        (event.status === '처리중' ||
        event.status === '처리완료'
          ? event.status
          : '탐지'),
    )

    setMemo(event.memo)
    setProcessedAt(event.processedAt)
  }, [event])

  /* 다른 이벤트를 열면 내부 상태 초기화 */
  useEffect(() => {
    setMemoModalOpen(false)
    setMemoInput('')
    setToast(undefined)
  }, [eventId])

  /* ESC 닫기 */
  useEffect(() => {
    if (!eventId) return

    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key !== 'Escape') return

      if (memoModalOpen) {
        setMemoModalOpen(false)
        return
      }

      onClose()
    }

    window.addEventListener(
      'keydown',
      handleKeyDown,
    )

    return () => {
      window.removeEventListener(
        'keydown',
        handleKeyDown,
      )
    }
  }, [eventId, memoModalOpen, onClose])

  /* 토스트 */
  useEffect(() => {
    if (!toast) return

    const timer = window.setTimeout(() => {
      setToast(undefined)
    }, 2600)

    return () => {
      window.clearTimeout(timer)
    }
  }, [toast])

  /* 증거 이미지 polling */
  const evidenceTriesRef = useRef(0)

  useEffect(() => {
    evidenceTriesRef.current = 0
  }, [eventId])

  useEffect(() => {
    if (
      !event ||
      event.evidenceImageUrl ||
      error
    ) {
      return
    }

    if (
      evidenceTriesRef.current >=
      EVIDENCE_POLL_MAX_TRIES
    ) {
      return
    }

    const timer = window.setInterval(() => {
      if (
        document.visibilityState !== 'visible'
      ) {
        return
      }

      if (
        evidenceTriesRef.current >=
        EVIDENCE_POLL_MAX_TRIES
      ) {
        window.clearInterval(timer)
        return
      }

      evidenceTriesRef.current += 1
      void refetch()
    }, EVIDENCE_POLL_INTERVAL_MS)

    return () => {
      window.clearInterval(timer)
    }
  }, [error, event, eventId, refetch])

  /* 경과시간 */
  const isOngoing =
    proc === '탐지' || proc === '처리중'

  const baseSec = useMemo(() => {
    if (!event?.occurredAt) return 0

    const seconds = Math.floor(
      (Date.now() -
        Date.parse(event.occurredAt)) /
        1000,
    )

    return Number.isFinite(seconds) &&
      seconds > 0
      ? seconds
      : 0
  }, [event?.occurredAt])

  const elapsed = useElapsed(
    Boolean(event) &&
      isOngoing &&
      !memoModalOpen,
    baseSec,
  )

  const changeProc = async (
    next: ProcessingStatus,
    note?: string,
  ) => {
    if (!event) return

    const previous = proc
    const previousMemo = memo
    const previousProcessedAt = processedAt

    setProc(next)

    if (note !== undefined) {
      setMemo(note)
    }

    if (next === '처리완료') {
      setProcessedAt(
        (prev) =>
          prev ??
          new Date()
            .toTimeString()
            .slice(0, 5),
      )
    }

    try {
      await updateStatus.mutateAsync({
        eventId:
          event.backendId ?? event.id,
        status: next,
        note,
      })

      setToast(
        previous === '처리완료' &&
          next === '처리완료'
          ? '처리 메모가 저장되었습니다'
          : next === '처리완료'
            ? '처리 완료되었습니다'
            : `처리 상태가 ${next}(으)로 변경되었습니다`,
      )

      onStatusChanged?.(event.id, next)
      void refetch()
    } catch (reason) {
      setProc(previous)
      setMemo(previousMemo)
      setProcessedAt(
        previousProcessedAt,
      )

      setToast(
        reason instanceof Error
          ? reason.message
          : '처리 상태 변경에 실패했습니다',
      )
    }
  }

  const isCompleted =
    proc === '처리완료'

  const onProcClick = (
    next: ProcessingStatus,
  ) => {
    if (isCompleted) return
    if (next === proc) return

    if (next === '처리완료') {
      setMemoInput(memo ?? '')
      setMemoModalOpen(true)
      return
    }

    void changeProc(next)
  }

  const openMemoEditor = () => {
    setMemoInput(memo ?? '')
    setMemoModalOpen(true)
  }

  const confirmComplete = (
    e: FormEvent<HTMLFormElement>,
  ) => {
    e.preventDefault()

    setMemoModalOpen(false)

    void changeProc(
      '처리완료',
      memoInput.trim() || undefined,
    )
  }

  if (!eventId) return null

  const portalTheme =
    document.documentElement.dataset.r0kiTheme ===
    'nocturne'
      ? 'nocturne'
      : 'crystal'

  return createPortal(
    <div
      className="r0ki event-detail-modal-portal"
      data-theme={portalTheme}
    >
      <div className="event-detail-modal-wrap">

        {/* 뒤 순찰 화면 가리기 */}
        <button
          type="button"
          className="event-detail-modal-backdrop"
          aria-label="이벤트 상세 닫기"
          onClick={onClose}
        />

        {/* 이벤트 상세 모달 */}
        <section
          className="event-detail-modal"
          role="dialog"
          aria-modal="true"
          aria-labelledby="event-detail-modal-title"
        >
          {/* 헤더 */}
          <div className="event-detail-modal-head">

            <div className="event-detail-modal-title-row">
              <h2 id="event-detail-modal-title">
                이벤트 상세
              </h2>

              {event && (
                <>
                  <span className="sub">
                    {event.id}
                  </span>

                  {event.riskLevel === '긴급' ? (
                    <span className="st u">
                      <i />
                      긴급
                    </span>
                  ) : (
                    <span className="st">
                      <i
                        style={{
                          background:
                            RISK_DOT[
                              event.riskLevel ??
                                ''
                            ] ??
                            'var(--detect)',
                        }}
                      />
                      {event.riskLevel ??
                        '보통'}
                    </span>
                  )}

                  <span
                    className="st"
                    data-status={
                      PROC_STATUS_ATTR[proc]
                    }
                  >
                    <i />
                    {proc}
                  </span>
                </>
              )}
            </div>

            {/* 우측 닫기 */}
            <button
              type="button"
              className="mdx event-detail-modal-close"
              aria-label="닫기"
              onClick={onClose}
            >
              <svg viewBox="0 0 24 24">
                <path d="M6 6l12 12M18 6L6 18" />
              </svg>
            </button>
          </div>

          {/* 본문 */}
          <div className="event-detail-modal-body">
            {error ? (
              <div className="glass g2 aisum">
                <div className="zh2">
                  <span className="zn">
                    이벤트를 불러오지 못했습니다
                  </span>
                </div>

                <button
                  type="button"
                  className="btn btn-s"
                  onClick={() =>
                    void refetch()
                  }
                >
                  다시 시도
                </button>
              </div>
            ) : !event ? (
              <div className="glass g2 aisum">
                <div className="zh2">
                  <span className="zn">
                    {isLoading
                      ? '불러오는 중…'
                      : `이벤트(${eventId})를 찾을 수 없습니다`}
                  </span>
                </div>
              </div>
            ) : (
              <div className="egrid">

                {/* 증거 이미지 */}
                <div
                  className="glass g2 dcol"
                  style={{
                    padding: 'var(--s5)',
                  }}
                >
                  <div className="zh2">
                    <span className="zn">
                      증거 이미지
                    </span>

                    <span className="zsub">
                      로봇 카메라 캡처 ·{' '}
                      {event.robotId}
                    </span>
                  </div>

                  <div className="ev">
                    {evidenceImageUrl ? (
                      <img
                        src={
                          evidenceImageUrl
                        }
                        alt={`${event.type} 증거 이미지`}
                      />
                    ) : (
                      <div className="mid">
                        <svg viewBox="0 0 24 24">
                          <path d="M3 8.5a2 2 0 0 1 2-2h2.2l1.3-2h6.9l1.3 2H19a2 2 0 0 1 2 2v9a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2z" />
                          <circle
                            cx="12"
                            cy="12.8"
                            r="3.6"
                          />
                        </svg>

                        <span>
                          {evidenceError
                            ? '증거 이미지를 불러오지 못했습니다.'
                            : isEvidenceLoading
                              ? '증거 이미지를 불러오는 중입니다.'
                              : '로봇의 증거 이미지 업로드를 기다리는 중입니다.'}
                        </span>

                        {evidenceError && (
                          <button
                            type="button"
                            className="btn btn-s"
                            onClick={() =>
                              void refetchEvidence()
                            }
                          >
                            다시 시도
                          </button>
                        )}
                      </div>
                    )}

                    <div className="hud">
                      <span className="corner c1" />
                      <span className="corner c2" />
                      <span className="corner c3" />
                      <span className="corner c4" />

                      <span className="rec">
                        <b />
                        녹화 · {event.robotId}
                      </span>

                      <span className="ts">
                        {event.time}
                      </span>
                    </div>
                  </div>
                </div>

                {/* 이벤트 정보 */}
                <div
                  className="glass g2 dcol"
                  style={{
                    padding: 'var(--s5)',
                  }}
                >
                  <div className="zh2">
                    <span className="zn">
                      이벤트 정보
                    </span>
                  </div>

                  <div className="event-detail-modal-info-scroll">
                    <div className="info">
                      <div className="ir">
                      <span className="k">
                        유형
                      </span>

                      <span className="v">
                        {event.type}

                        {event.subType
                          ? ` (${event.subType})`
                          : ''}
                      </span>
                    </div>

                    <div className="ir">
                      <span className="k">
                        탐지 날짜
                      </span>

                      <span className="v num">
                        {event.occurredAtLabel ??
                          event.time}
                      </span>
                    </div>

                    <div className="ir">
                      <span className="k">
                        위치
                      </span>

                      <span className="v">
                        {event.location}
                      </span>
                    </div>

                    <div className="ir">
                      <span className="k">
                        탐지 로봇
                      </span>

                      <span className="v num">
                        {event.robotId}
                      </span>
                    </div>

                    <div className="ir">
                      <span className="k">
                        신뢰도
                      </span>

                      <span className="v num">
                        {event.confidence != null
                          ? `${event.confidence}%`
                          : '-'}
                      </span>
                    </div>

                    {proc ===
                      '처리완료' &&
                    processedAt ? (
                      <div className="ir">
                        <span className="k">
                          처리시각
                        </span>

                        <span className="v num">
                          {processedAt}
                        </span>
                      </div>
                    ) : (
                      <div className="ir">
                        <span className="k">
                          경과시간
                        </span>

                        <span className="v num">
                          {elapsed}
                        </span>
                      </div>
                    )}

                    {proc !== '탐지' &&
                      event.assignee && (
                        <div className="ir">
                          <span className="k">
                            담당자
                          </span>

                          <span className="v">
                            {event.assignee}
                          </span>
                        </div>
                      )}

                    <div className="ir">
                      <span className="k">
                        처리 상태
                      </span>

                      <span className="v">
                        <span
                          className="st"
                          data-status={
                            PROC_STATUS_ATTR[
                              proc
                            ]
                          }
                        >
                          <i />
                          {proc}
                        </span>
                      </span>
                      </div>
                    </div>
                  </div>

                  {/* 처리 메모 */}
                  {isCompleted && (
                    <div className="memo">
                      <span className="k">
                        처리 메모
                      </span>

                      <span className="t">
                        {memo?.trim()
                          ? memo
                          : '작성된 메모가 없습니다'}
                      </span>

                      <button
                        type="button"
                        className="btn btn-s"
                        disabled={
                          updateStatus.isPending
                        }
                        onClick={
                          openMemoEditor
                        }
                      >
                        메모 수정
                      </button>
                    </div>
                  )}

                  {/* 처리 상태 변경 */}
                  <div
                    className={`actwrap event-detail-actions${isCompleted ? ' completed' : ''}`}
                  >
                    {isCompleted && (
                      <div className="actk">
                        처리 완료된 이벤트는 상태를 변경할 수 없습니다
                      </div>
                    )}

                    <div className="acts">
                      {PROC_STATUSES.map(
                        (status) => (
                          <button
                            key={status}
                            type="button"
                            data-status={
                              PROC_STATUS_ATTR[
                                status
                              ]
                            }
                            aria-pressed={
                              proc === status
                            }
                            disabled={
                              updateStatus.isPending ||
                              isCompleted
                            }
                            onClick={() =>
                              onProcClick(
                                status,
                              )
                            }
                          >
                            {status}
                          </button>
                        ),
                      )}
                    </div>
                  </div>
                </div>
              </div>
            )}
          </div>
        </section>
      </div>

      {/* 처리완료 / 메모수정 모달 */}
      {memoModalOpen && (
        <div className="modalwrap event-memo-modal">
          <div
            className="backdrop"
            onClick={() =>
              setMemoModalOpen(false)
            }
          />

          <div
            className="modal glass g3"
            role="dialog"
            aria-modal="true"
            aria-labelledby="event-memo-modal-title"
          >
            <div className="mdhead">
              <h2 id="event-memo-modal-title">
                {isCompleted
                  ? '메모 수정'
                  : '처리 완료'}
              </h2>

              <button
                type="button"
                className="mdx"
                aria-label="닫기"
                onClick={() =>
                  setMemoModalOpen(false)
                }
              >
                <svg viewBox="0 0 24 24">
                  <path d="M6 6l12 12M18 6L6 18" />
                </svg>
              </button>
            </div>

            <form
              onSubmit={confirmComplete}
            >
              <label
                className="mdlabel"
                htmlFor="event-modal-memo"
              >
                처리 메모
              </label>

              <textarea
                id="event-modal-memo"
                rows={3}
                value={memoInput}
                onChange={(e) =>
                  setMemoInput(
                    e.target.value,
                  )
                }
                placeholder="예: 경비팀 현장 확인 완료"
                autoFocus
              />

              <p className="mdhelp">
                선택 입력 — 비워도 완료할 수 있습니다
              </p>

              <div className="mdact">
                <button
                  type="button"
                  className="btn btn-s"
                  onClick={() =>
                    setMemoModalOpen(false)
                  }
                >
                  취소
                </button>

                <button
                  type="submit"
                  className="btn btn-p"
                >
                  {isCompleted
                    ? '메모 저장'
                    : '완료 처리'}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}

      {/* 토스트 */}
      <div
        className={`toast${toast ? ' on' : ''}`}
        role="status"
        aria-live="polite"
      >
        <svg viewBox="0 0 24 24">
          <path d="M4 12.5 9.5 18 20 6.5" />
        </svg>

        <span>{toast}</span>
      </div>
    </div>,
    document.body,
  )
}
