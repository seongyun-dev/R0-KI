import { useMjpegStream } from './useMjpegStream'

/* R0-Ki 실시간 탐지 영상 (시안 §11-2 그대로 포팅)
   어두운 영상 위 HUD — 바운딩 박스 + 스캔라인 + 코너 마커 + REC.
   이 영역은 어둡기 때문에 유리 대비 검증에서 제외(자체 밝은 색 사용).
   지금은 시안의 데모 씬(더미). 실제 영상 스트림 연동 시 교체. */

export type R0KiLiveCamProps = {
  /** 긴급 감지 여부 — 긴급 바운딩 박스 표시 */
  urgent?: boolean
  clockText?: string
  robotId?: string | number
}

export function R0KiLiveCam({ urgent = false, clockText, robotId }: R0KiLiveCamProps) {
  const { frameUrl, state } = useMjpegStream(robotId)

  return (
    <div className="cam">
      {frameUrl && (
        <img className="camstream" src={frameUrl} alt="로봇 좌우 카메라 AI 실시간 탐지 영상" />
      )}
      {!frameUrl && <svg viewBox="0 0 320 200" preserveAspectRatio="xMidYMid slice" aria-label="로봇 전방 카메라 실시간 영상">
        <defs>
          <linearGradient id="camsky" x1="0" y1="0" x2="0" y2="1">
            <stop offset="0" stopColor="#243447" /><stop offset=".55" stopColor="#3A4E66" /><stop offset="1" stopColor="#1B2836" />
          </linearGradient>
          <linearGradient id="camfloor" x1="0" y1="0" x2="0" y2="1">
            <stop offset="0" stopColor="#4A6076" /><stop offset="1" stopColor="#22303F" />
          </linearGradient>
          <linearGradient id="camlight" x1="0" y1="0" x2="0" y2="1">
            <stop offset="0" stopColor="#FFF6DC" stopOpacity=".30" /><stop offset="1" stopColor="#FFF6DC" stopOpacity="0" />
          </linearGradient>
        </defs>
        <rect width="320" height="200" fill="url(#camsky)" />
        <path d="M0 200 L104 96 L216 96 L320 200Z" fill="url(#camfloor)" />
        <g stroke="#8FA6BC" strokeOpacity=".18" strokeWidth="1">
          <path d="M104 96 L0 200M216 96 L320 200M96 120H224M80 146H240M56 176H264" />
        </g>
        <rect x="104" y="42" width="112" height="54" fill="#1E2B3A" />
        <rect x="120" y="54" width="80" height="30" rx="3" fill="#2C3E52" />
        <path d="M132 42 h56 l-6 -14 h-44Z" fill="url(#camlight)" />
        <rect x="0" y="42" width="104" height="88" fill="#26374A" />
        <rect x="216" y="42" width="104" height="88" fill="#22323F" />
        <rect x="30" y="70" width="40" height="60" rx="2" fill="#33475C" />
        <rect x="250" y="66" width="46" height="64" rx="2" fill="#2C3E50" />
        <g className="camsub">
          <ellipse cx="150" cy="152" rx="30" ry="5" fill="#0B121B" opacity=".55" />
          <rect x="130" y="136" width="42" height="15" rx="7" fill="#4C5F76" />
          <circle cx="176" cy="143" r="7.5" fill="#5A6E86" />
          <rect x="126" y="142" width="12" height="8" rx="4" fill="#41536A" />
        </g>
        {urgent && (
          <g className="bbox">
            <rect x="118" y="128" width="70" height="30" fill="none" stroke="#FF6169" strokeWidth="1.8" />
            <path d="M118 136V128h9M188 128h-9M188 158v-8M118 150v8h9" stroke="#fff" strokeWidth="2" fill="none" />
            <rect x="118" y="116" width="72" height="12" fill="#C0272D" />
            <text x="121" y="125" fontSize="8" fontWeight="700" fill="#FFFFFF" fontFamily="Pretendard, sans-serif">쓰러짐 0.96 · 긴급</text>
          </g>
        )}
        <g className="bbox b2">
          <rect x="248" y="64" width="50" height="68" fill="none" stroke="var(--detect)" strokeWidth="1.2" strokeDasharray="4 3" />
          <rect x="248" y="52" width="48" height="12" fill="var(--detect)" />
          <text x="251" y="61" fontSize="8" fontWeight="700" fill="#052A47" fontFamily="Pretendard, sans-serif">출입문 0.72</text>
        </g>
        <rect className="scanline" x="0" y="0" width="320" height="3" fill="#BFE7FF" opacity=".22" />
        <g stroke="#CFE6FA" strokeOpacity=".5" strokeWidth="1.2" fill="none">
          <path d="M10 22V10h14M310 22V10h-14M10 178v12h14M310 178v12h-14" />
        </g>
        <g fontSize="8" fill="#DCEBF8" opacity=".9" fontFamily="Pretendard, sans-serif" fontWeight="600">
          <text x="12" y="17">카메라 01 · 전방</text>
          <text x="308" y="17" textAnchor="end">1920×1080</text>
          <text x="12" y="193">101동 지하주차장 지하 1층</text>
          <text x="308" y="193" textAnchor="end">적외선 꺼짐</text>
        </g>
      </svg>}
      <span className={`camstate ${state}`}>
        {state === 'live'
          ? '좌·우 AI 탐지'
          : state === 'connecting' || state === 'waiting'
            ? '영상 연결 중'
            : '영상 대기'}
        {clockText ? ` · ${clockText}` : ''}
      </span>
      <span className={`rec${state === 'live' ? '' : ' paused'}`} />
    </div>
  )
}
