import { useEffect, useMemo, useRef, useState, type FormEvent } from 'react'
import { Link, useParams } from 'react-router-dom'
import { R0KiShell } from '../components/layout/R0KiShell'
import { useEvent, useEvidenceImage, useUpdateEventStatus } from '../features/events/useEvents'
import { useElapsed } from '../lib/useElapsed'
import type { ProcessingStatus } from '../types/domain'

/* R0-Ki 이벤트 상세 — 시안 R0Kievents 그대로.
   증거 이미지(HUD) + 이벤트 정보 + 처리 상태 컨트롤(처리완료 시 메모 모달).
   한 화면 고정 — 정보 리스트만 내부 스크롤. 데이터/뮤테이션은 기존 훅 그대로. */

const PROC_STATUSES: ProcessingStatus[] = ['탐지', '처리중', '처리완료']

/* 증거 이미지는 로봇이 이벤트를 등록한 뒤 따로 올린다. 잠깐 기다리면 붙으므로
   짧은 주기로 다시 조회하되 상한을 둔다 — 끝내 증거가 올라오지 않는 이벤트를
   열어두면 탭을 닫을 때까지 계속 서버를 두드리게 된다. */
const EVIDENCE_POLL_INTERVAL_MS = 5000
const EVIDENCE_POLL_MAX_TRIES = 12 // 5초 × 12 = 약 1분

/* 상태 점 색 — 명도 램프 */
const STATE_DOT: Record<string, string> = {
  탐지: 'var(--detect)',
  처리중: 'var(--charge)',
  처리완료: 'var(--offline)',
}
const RISK_DOT: Record<string, string> = {
  보통: 'var(--detect)',
  낮음: 'var(--offline)',
}

export default function EventDetail() {
  const { id } = useParams()
  const { data: event, isLoading, error, refetch } = useEvent(id)
  const {
    data: evidenceImageUrl,
    isLoading: isEvidenceLoading,
    error: evidenceError,
    refetch: refetchEvidence,
  } = useEvidenceImage(event?.evidenceImageUrl)
  const updateStatus = useUpdateEventStatus()

  // 처리 상태 — 서버 값으로 초기화 후 낙관적 갱신
  const [proc, setProc] = useState<ProcessingStatus>('탐지')
  const [memo, setMemo] = useState<string>()
  const [processedAt, setProcessedAt] = useState<string>()
  // 처리완료 메모 입력 모달
  const [memoModalOpen, setMemoModalOpen] = useState(false)
  const [memoInput, setMemoInput] = useState('')
  // 토스트
  const [toast, setToast] = useState<string>()

  useEffect(() => {
    if (!event) return
    setProc(event.processingStatus ?? (event.status === '처리중' || event.status === '처리완료' ? event.status : '탐지'))
    setMemo(event.memo)
    setProcessedAt(event.processedAt)
  }, [event])

  useEffect(() => {
    if (!toast) return
    const t = setTimeout(() => setToast(undefined), 2600)
    return () => clearTimeout(t)
  }, [toast])

  // 재조회 횟수는 effect 재실행(refetch → event 갱신)을 건너뛰어 누적돼야 하므로 ref 로 센다
  const evidenceTriesRef = useRef(0)
  useEffect(() => {
    evidenceTriesRef.current = 0
  }, [id])

  useEffect(() => {
    if (!event || event.evidenceImageUrl || error) return
    if (evidenceTriesRef.current >= EVIDENCE_POLL_MAX_TRIES) return
    const timer = window.setInterval(() => {
      // 백그라운드 탭에서는 횟수를 쓰지 않고 건너뛴다 — 돌아왔을 때 남은 기회로 확인한다
      if (document.visibilityState !== 'visible') return
      if (evidenceTriesRef.current >= EVIDENCE_POLL_MAX_TRIES) {
        window.clearInterval(timer)
        return
      }
      evidenceTriesRef.current += 1
      refetch()
    }, EVIDENCE_POLL_INTERVAL_MS)
    return () => window.clearInterval(timer)
  }, [error, event, id, refetch])

  // 경과시간 — 탐지/처리중일 때만 실시간 카운트. 메모 모달 중엔 멈춤(포커스 튐 방지)
  const isOngoing = proc === '탐지' || proc === '처리중'
  const baseSec = useMemo(() => {
    if (!event?.occurredAt) return 0
    const s = Math.floor((Date.now() - Date.parse(event.occurredAt)) / 1000)
    return Number.isFinite(s) && s > 0 ? s : 0
  }, [event?.occurredAt])
  const elapsed = useElapsed(Boolean(event) && isOngoing && !memoModalOpen, baseSec)

  const changeProc = async (next: ProcessingStatus, note?: string) => {
    if (!event) return
    const previous = proc
    setProc(next)
    if (note !== undefined) setMemo(note)
    if (next === '처리완료') {
      setProcessedAt((prev) => prev ?? new Date().toTimeString().slice(0, 5))
    }
    try {
      await updateStatus.mutateAsync({ eventId: event.backendId ?? event.id, status: next, note })
      setToast(next === '처리완료' ? '처리 완료되었습니다' : `처리 상태가 ${next}(으)로 변경되었습니다`)
    } catch (reason) {
      setProc(previous)
      setToast(reason instanceof Error ? reason.message : '처리 상태 변경에 실패했습니다')
    }
  }

  // 처리완료는 바로 바꾸지 않고 메모 모달을 먼저 연다
  const onProcClick = (next: ProcessingStatus) => {
    if (next === proc) return
    if (next === '처리완료') {
      setMemoInput(memo ?? '')
      setMemoModalOpen(true)
      return
    }
    void changeProc(next)
  }

  const confirmComplete = (e: FormEvent<HTMLFormElement>) => {
    e.preventDefault()
    setMemoModalOpen(false)
    void changeProc('처리완료', memoInput.trim() || undefined)
  }

  return (
    <R0KiShell active="events">
      <div className="pcol">
        <div className="pagehead">
          <div>
            <div className="crumb">
              <Link to="/app">대시보드</Link><i>›</i>
              <Link to="/app/events">이벤트 관리</Link><i>›</i>
              <b>{event?.id ?? id}</b>
            </div>
            <div className="ptitle row">
              이벤트 상세
              {event && (
                <>
                  <span className="sub">{event.id}</span>
                  {event.riskLevel === '긴급' ? (
                    <span className="st u"><i />긴급</span>
                  ) : (
                    <span className="st">
                      <i style={{ background: RISK_DOT[event.riskLevel ?? ''] ?? 'var(--detect)' }} />
                      {event.riskLevel ?? '보통'}
                    </span>
                  )}
                  <span className="st">
                    <i style={{ background: STATE_DOT[proc] }} />
                    {proc}
                  </span>
                </>
              )}
            </div>
          </div>
        </div>
        {error ? (
          <div className="glass g2 aisum">
            <div className="zh2"><span className="zn">이벤트를 불러오지 못했습니다</span></div>
            <button type="button" className="btn btn-s" onClick={refetch}>다시 시도</button>
          </div>
        ) : !event ? (
          <div className="glass g2 aisum">
            <div className="zh2">
              <span className="zn">{isLoading ? '불러오는 중…' : `이벤트(${id})를 찾을 수 없습니다`}</span>
            </div>
            {!isLoading && <Link to="/app/events" className="btn btn-s">목록으로</Link>}
          </div>
        ) : (
          <div className="egrid">
            {/* 증거 이미지 */}
            <div className="glass g2 dcol" style={{ padding: 'var(--s5)' }}>
              <div className="zh2">
                <span className="zn">증거 이미지</span>
                <span className="zsub">로봇 카메라 캡처 · {event.robotId}</span>
              </div>
              <div className="ev">
                {evidenceImageUrl ? (
                  <img src={evidenceImageUrl} alt={`${event.type} 증거 이미지`} />
                ) : (
                  <div className="mid">
                    <svg viewBox="0 0 24 24">
                      <path d="M3 8.5a2 2 0 0 1 2-2h2.2l1.3-2h6.9l1.3 2H19a2 2 0 0 1 2 2v9a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2z" />
                      <circle cx="12" cy="12.8" r="3.6" />
                    </svg>
                    <span>
                      {evidenceError
                        ? '증거 이미지를 불러오지 못했습니다.'
                        : isEvidenceLoading
                          ? '증거 이미지를 불러오는 중입니다.'
                          : '로봇의 증거 이미지 업로드를 기다리는 중입니다.'}
                    </span>
                    {evidenceError && (
                      <button type="button" className="btn btn-s" onClick={refetchEvidence}>
                        다시 시도
                      </button>
                    )}
                  </div>
                )}
                <div className="hud">
                  <span className="corner c1" /><span className="corner c2" />
                  <span className="corner c3" /><span className="corner c4" />
                  <span className="rec"><b />녹화 · {event.robotId}</span>
                  <span className="ts">{event.time}</span>
                </div>
              </div>
            </div>

            {/* 이벤트 정보 */}
            <div className="glass g2 dcol" style={{ padding: 'var(--s5)' }}>
              <div className="zh2"><span className="zn">이벤트 정보</span></div>

              <div className="info">
                <div className="ir">
                  <span className="k">유형</span>
                  <span className="v">{event.type}{event.subType ? ` (${event.subType})` : ''}</span>
                </div>
                <div className="ir">
                  <span className="k">탐지 시각</span>
                  <span className="v num">{event.time}</span>
                </div>
                <div className="ir">
                  <span className="k">위치</span>
                  <span className="v">{event.location}</span>
                </div>
                <div className="ir">
                  <span className="k">탐지 로봇</span>
                  <span className="v num">{event.robotId}</span>
                </div>
                <div className="ir">
                  <span className="k">신뢰도</span>
                  <span className="v num">{event.confidence != null ? `${event.confidence}%` : '-'}</span>
                </div>
                {proc === '처리완료' && processedAt ? (
                  <div className="ir">
                    <span className="k">처리시각</span>
                    <span className="v num">{processedAt}</span>
                  </div>
                ) : (
                  <div className="ir">
                    <span className="k">경과시간</span>
                    <span className="v num">{elapsed}</span>
                  </div>
                )}
                {proc !== '탐지' && event.assignee && (
                  <div className="ir">
                    <span className="k">담당자</span>
                    <span className="v">{event.assignee}</span>
                  </div>
                )}
                <div className="ir">
                  <span className="k">처리 상태</span>
                  <span className="v">
                    <span className="st"><i style={{ background: STATE_DOT[proc] }} />{proc}</span>
                  </span>
                </div>
              </div>

              {/* 처리 메모 — 완료 후 표시 */}
              {proc === '처리완료' && memo && (
                <div className="memo">
                  <span className="k">처리 메모</span>
                  <span className="t">{memo}</span>
                </div>
              )}

              {/* 처리 상태 — 경비원이 직접 변경 */}
              <div className="actwrap">
                <div className="actk">처리 상태 — 경비원이 직접 변경 (기본: 탐지)</div>
                <div className="acts">
                  {PROC_STATUSES.map((s) => (
                    <button
                      key={s}
                      type="button"
                      aria-pressed={proc === s}
                      disabled={updateStatus.isPending || proc === '처리완료'}
                      onClick={() => onProcClick(s)}
                    >
                      {s}
                    </button>
                  ))}
                </div>
              </div>
            </div>
          </div>
        )}
      </div>

      {/* 처리 완료 메모 모달 */}
      {memoModalOpen && (
        <div className="modalwrap">
          <div className="backdrop" onClick={() => setMemoModalOpen(false)} />
          <div className="modal glass g3" role="dialog" aria-modal="true" aria-labelledby="md-title">
            <div className="mdhead">
              <h2 id="md-title">처리 완료</h2>
              <button type="button" className="mdx" aria-label="닫기" onClick={() => setMemoModalOpen(false)}>
                <svg viewBox="0 0 24 24"><path d="M6 6l12 12M18 6L6 18" /></svg>
              </button>
            </div>
            <form onSubmit={confirmComplete}>
              <label className="mdlabel" htmlFor="memo-in">처리 메모</label>
              <textarea
                id="memo-in"
                rows={3}
                value={memoInput}
                onChange={(e) => setMemoInput(e.target.value)}
                placeholder="예: 경비팀 현장 확인 완료"
                autoFocus
              />
              <p className="mdhelp">선택 입력 — 비워도 완료할 수 있습니다</p>
              <div className="mdact">
                <button type="button" className="btn btn-s" onClick={() => setMemoModalOpen(false)}>취소</button>
                <button type="submit" className="btn btn-p">완료 처리</button>
              </div>
            </form>
          </div>
        </div>
      )}

      {/* 토스트 */}
      <div className={`toast${toast ? ' on' : ''}`} role="status" aria-live="polite">
        <svg viewBox="0 0 24 24"><path d="M4 12.5 9.5 18 20 6.5" /></svg>
        <span>{toast}</span>
      </div>
    </R0KiShell>
  )
}
