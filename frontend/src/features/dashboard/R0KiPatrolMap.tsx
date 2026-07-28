/* R0-Ki 순찰 지도 (시안 R0-Ki-preview.html §11-1 기반)
   단지 경계·건물·시설 + 순찰 경로(완료 실선/잔여 점선) + 웨이포인트 12개 + 로봇 마커.
   ⚠️ 뷰박스를 1020×900(1.13:1) → 1377×900(1.53:1)으로 넓혔다.
      와이드 화면에서 meet 정렬 시 좌우에 각 185px씩 빈 공간이 생겨,
      가로 좌표를 1.35배로 펼쳐 화면을 채운다.
      원(웨이포인트·놀이터)은 반지름을 유지해 타원으로 찌그러지지 않는다.
   지금은 시안의 데모 맵(더미). 실제 맵 API 연동 시 좌표만 바꿔 끼운다. */

export type R0KiPatrolMapProps = {
  /** 긴급 이벤트 발생 시 지도에 응급 마커 표시 */
  urgent?: { label: string } | null
  robotName?: string
}

export function R0KiPatrolMap({ urgent, robotName = 'R0-Ki 1호기' }: R0KiPatrolMapProps) {
  return (
    <svg viewBox="0 0 1377 900" preserveAspectRatio="xMidYMid meet" aria-label="아파트 단지 순찰 지도">
      <defs>
        <radialGradient id="botHalo">
          <stop offset="0" stopColor="var(--graphic)" stopOpacity=".40" />
          <stop offset="1" stopColor="var(--graphic)" stopOpacity="0" />
        </radialGradient>
        <linearGradient id="coneMap" x1="0" y1="0" x2="1" y2="0">
          <stop offset="0" stopColor="var(--graphic)" stopOpacity=".38" />
          <stop offset="1" stopColor="var(--graphic)" stopOpacity="0" />
        </linearGradient>
      </defs>

      {/* 그리드 */}
      <g stroke="currentColor" opacity=".08" strokeWidth="1">
        <path d="M0 75H1377M0 150H1377M0 225H1377M0 300H1377M0 375H1377M0 450H1377M0 525H1377M0 600H1377M0 675H1377M0 750H1377M0 825H1377" />
        <path d="M115 0V900M230 0V900M345 0V900M460 0V900M575 0V900M690 0V900M805 0V900M920 0V900M1035 0V900M1150 0V900M1265 0V900" />
      </g>

      {/* 단지 경계 · 출입구 */}
      <path
        d="M35 40 a14 14 0 0 1 14-14 h612 M783 26 h545 a14 14 0 0 1 14 14 v824 a14 14 0 0 1-14 14 H49 a14 14 0 0 1-14-14 V300 M35 240 V40"
        fill="none" stroke="currentColor" strokeOpacity=".22" strokeWidth="1.6" strokeDasharray="10 8"
      />
      <g className="gate">
        <path d="M661 26 H783" stroke="var(--graphic)" strokeWidth="4" strokeLinecap="round" />
        <text x="722" y="50">후문</text>
        <path d="M35 240 V300" stroke="var(--graphic)" strokeWidth="4" strokeLinecap="round" />
        <text x="70" y="276" textAnchor="start">정문</text>
      </g>
      <text className="maplbl" x="51" y="892" textAnchor="start">단지 외곽 · 순찰 경계</text>

      {/* 건물 · 시설 */}
      <g fill="currentColor" opacity=".075">
        <rect x="202" y="60" width="290" height="130" rx="10" />
        <rect x="540" y="60" width="290" height="130" rx="10" />
        <rect x="878" y="60" width="290" height="130" rx="10" />
        <rect x="202" y="280" width="392" height="200" rx="10" />
        <rect x="641" y="280" width="202" height="200" rx="10" />
        <rect x="891" y="280" width="277" height="200" rx="10" />
        <rect x="202" y="580" width="290" height="150" rx="10" />
        <rect x="540" y="580" width="290" height="150" rx="10" />
        <rect x="878" y="580" width="290" height="150" rx="10" />
      </g>
      <g fill="none" stroke="currentColor" strokeOpacity=".16" strokeWidth="1.4">
        <rect x="202" y="60" width="290" height="130" rx="10" />
        <rect x="540" y="60" width="290" height="130" rx="10" />
        <rect x="878" y="60" width="290" height="130" rx="10" />
        <rect x="202" y="280" width="392" height="200" rx="10" />
        <rect x="641" y="280" width="202" height="200" rx="10" />
        <rect x="891" y="280" width="277" height="200" rx="10" />
        <rect x="202" y="580" width="290" height="150" rx="10" />
        <rect x="540" y="580" width="290" height="150" rx="10" />
        <rect x="878" y="580" width="290" height="150" rx="10" />
      </g>

      {/* 지상주차장 주차면 */}
      <g stroke="currentColor" strokeOpacity=".22" strokeWidth="1.2">
        <path d="M232 340H354M232 380H354M232 420H354M232 460H354" />
        <path d="M232 334V466" />
        <path d="M446 340H567M446 380H567M446 420H567M446 460H567" />
        <path d="M567 334V466" />
      </g>
      <g fill="currentColor" opacity=".14">
        <rect x="240" y="347" width="103" height="25" rx="3" />
        <rect x="240" y="427" width="103" height="25" rx="3" />
        <rect x="456" y="387" width="103" height="25" rx="3" />
      </g>

      {/* 놀이터 */}
      <g stroke="currentColor" strokeOpacity=".22" strokeWidth="1.3" fill="none">
        <circle cx="742" cy="372" r="44" />
        <path d="M705 446h76M716 446v-20M770 446v-20" />
      </g>

      {/* 분리수거장 수거함 */}
      <g stroke="currentColor" strokeOpacity=".24" strokeWidth="1.3" fill="currentColor" fillOpacity=".08">
        <rect x="923" y="356" width="49" height="60" rx="5" />
        <rect x="983" y="356" width="49" height="60" rx="5" />
        <rect x="1042" y="356" width="49" height="60" rx="5" />
        <rect x="1102" y="356" width="49" height="60" rx="5" />
      </g>

      <g className="maplbl" textAnchor="middle">
        <text x="347" y="130">101동</text>
        <text x="684" y="130">102동</text>
        <text x="1022" y="130">103동</text>
        <text x="398" y="310">지상주차장</text>
        <text x="742" y="310">놀이터</text>
        <text x="1029" y="310">분리수거장</text>
        <text x="347" y="662">104동</text>
        <text x="684" y="662">커뮤니티센터</text>
        <text x="1022" y="650">지하주차장 진입</text>
        <text x="1022" y="674">지하 1~2층</text>
      </g>

      {/* 순찰 경로 — 잔여 점선 / 완료 실선 */}
      <path
        d="M128 800 L128 230 L1296 230 L1296 800 Z"
        fill="none" stroke="var(--graphic)" strokeOpacity=".24" strokeWidth="3.4"
        strokeLinecap="round" strokeLinejoin="round" strokeDasharray="10 9"
      />
      <path
        d="M128 800 L128 230 L1296 230 L1296 340"
        fill="none" stroke="var(--graphic)" strokeWidth="6" strokeLinecap="round" strokeLinejoin="round"
      />

      <g className="station">
        <rect x="202" y="816" width="151" height="34" rx="10" />
        <text x="278" y="838">경비실 · 충전소</text>
      </g>

      {/* 웨이포인트 12개 — 완료 채운 원 / 미완료 빈 원 */}
      <g className="wp">
        <g><circle cx="128" cy="800" r="7" /><text x="176" y="805" textAnchor="start">1번</text></g>
        <g><circle cx="128" cy="515" r="7" /><text x="176" y="520" textAnchor="start">2번</text></g>
        <g><circle cx="128" cy="230" r="7" /><text x="176" y="213" textAnchor="start">3번</text></g>
        <g><circle cx="405" cy="230" r="7" /><text x="405" y="213">4번 · 101동</text></g>
        <g><circle cx="742" cy="230" r="7" /><text x="742" y="213">5번 · 102동</text></g>
        <g><circle cx="1067" cy="230" r="7" /><text x="1067" y="213">6번 · 103동</text></g>
        <g><circle cx="1296" cy="230" r="7" /><text x="1247" y="213" textAnchor="end">7번</text></g>
        <g className="pend"><circle cx="1296" cy="515" r="7" /><text x="1247" y="520" textAnchor="end">8번</text></g>
        <g className="pend"><circle cx="1296" cy="800" r="7" /><text x="1247" y="805" textAnchor="end">9번</text></g>
        <g className="pend"><circle cx="1026" cy="800" r="7" /><text x="1026" y="784">10번 · 지하주차장</text></g>
        <g className="pend"><circle cx="702" cy="800" r="7" /><text x="702" y="784">11번 · 커뮤니티</text></g>
        <g className="pend"><circle cx="405" cy="800" r="7" /><text x="405" y="784">12번 · 104동</text></g>
      </g>

      {/* 긴급 마커 — 긴급 이벤트가 있을 때만 */}
      {urgent && (
        <g className="alertpt">
          <circle className="ping2" cx="1193" cy="452" r="12" fill="none" stroke="var(--urgent)" strokeWidth="2.4" />
          <circle cx="1193" cy="452" r="8" fill="var(--urgent)" />
          <text x="1183" y="428" textAnchor="end">{urgent.label}</text>
        </g>
      )}

      {/* 로봇 — 헤일로 + 스캔 콘 + 확산 링 */}
      <g className="bot" transform="translate(1296,340) rotate(90)">
        <circle r="80" fill="url(#botHalo)" />
        <path d="M0 0 L104 -50 A116 116 0 0 1 104 50 Z" fill="url(#coneMap)" />
        <circle className="ping" r="18" fill="none" stroke="var(--graphic)" strokeWidth="2.6" />
        <circle r="13" fill="var(--graphic)" />
        <circle r="13" fill="none" stroke="#fff" strokeOpacity=".92" strokeWidth="2.8" />
        <circle r="5" fill="#fff" />
      </g>
      <text className="botlbl" x="1199" y="346" textAnchor="end">{robotName}</text>

      {/* 축척 · 방위 */}
      <g className="scale">
        <path d="M1053 860 H1215" stroke="currentColor" strokeOpacity=".45" strokeWidth="2" />
        <path d="M1053 854V866M1215 854V866" stroke="currentColor" strokeOpacity=".45" strokeWidth="2" />
        <text x="1134" y="848">30미터</text>
      </g>
      <g className="compass" transform="translate(1298,62)">
        <circle r="17" fill="none" stroke="currentColor" strokeOpacity=".25" strokeWidth="1.4" />
        <path d="M0 -12 L5.5 4 L0 0 L-5.5 4 Z" fill="var(--graphic)" />
        <text y="-22">북</text>
      </g>
    </svg>
  )
}
