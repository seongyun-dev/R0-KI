/* R0-Ki 순찰 지도 (시안 R0-Ki-preview.html §11-1 그대로 포팅)
   단지 경계·건물·시설 + 순찰 경로(완료 실선/잔여 점선) + 웨이포인트 12개 + 로봇 마커.
   지금은 시안의 데모 맵(더미). 실제 맵 API 연동 시 좌표만 바꿔 끼운다. */

export type R0KiPatrolMapProps = {
  /** 긴급 이벤트 발생 시 지도에 응급 마커 표시 */
  urgent?: { label: string } | null
  robotName?: string
}

export function R0KiPatrolMap({ urgent, robotName = 'R0-Ki 1호기' }: R0KiPatrolMapProps) {
  return (
    <svg viewBox="0 0 1020 900" preserveAspectRatio="xMidYMid meet" aria-label="아파트 단지 순찰 지도">
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
        <path d="M0 75H1020M0 150H1020M0 225H1020M0 300H1020M0 375H1020M0 450H1020M0 525H1020M0 600H1020M0 675H1020M0 750H1020M0 825H1020" />
        <path d="M85 0V900M170 0V900M255 0V900M340 0V900M425 0V900M510 0V900M595 0V900M680 0V900M765 0V900M850 0V900M935 0V900" />
      </g>

      {/* 단지 경계 · 출입구 */}
      <path
        d="M26 40 a14 14 0 0 1 14-14 h450 M580 26 h414 a14 14 0 0 1 14 14 v824 a14 14 0 0 1-14 14 H40 a14 14 0 0 1-14-14 V300 M26 240 V40"
        fill="none" stroke="currentColor" strokeOpacity=".22" strokeWidth="1.6" strokeDasharray="10 8"
      />
      <g className="gate">
        <path d="M490 26 H580" stroke="var(--graphic)" strokeWidth="4" strokeLinecap="round" />
        <text x="535" y="50">후문</text>
        <path d="M26 240 V300" stroke="var(--graphic)" strokeWidth="4" strokeLinecap="round" />
        <text x="52" y="276" textAnchor="start">정문</text>
      </g>
      <text className="maplbl" x="38" y="892" textAnchor="start">단지 외곽 · 순찰 경계</text>

      {/* 건물 · 시설 */}
      <g fill="currentColor" opacity=".075">
        <rect x="150" y="60" width="215" height="130" rx="10" />
        <rect x="400" y="60" width="215" height="130" rx="10" />
        <rect x="650" y="60" width="215" height="130" rx="10" />
        <rect x="150" y="280" width="290" height="200" rx="10" />
        <rect x="475" y="280" width="150" height="200" rx="10" />
        <rect x="660" y="280" width="205" height="200" rx="10" />
        <rect x="150" y="580" width="215" height="150" rx="10" />
        <rect x="400" y="580" width="215" height="150" rx="10" />
        <rect x="650" y="580" width="215" height="150" rx="10" />
      </g>
      <g fill="none" stroke="currentColor" strokeOpacity=".16" strokeWidth="1.4">
        <rect x="150" y="60" width="215" height="130" rx="10" />
        <rect x="400" y="60" width="215" height="130" rx="10" />
        <rect x="650" y="60" width="215" height="130" rx="10" />
        <rect x="150" y="280" width="290" height="200" rx="10" />
        <rect x="475" y="280" width="150" height="200" rx="10" />
        <rect x="660" y="280" width="205" height="200" rx="10" />
        <rect x="150" y="580" width="215" height="150" rx="10" />
        <rect x="400" y="580" width="215" height="150" rx="10" />
        <rect x="650" y="580" width="215" height="150" rx="10" />
      </g>

      {/* 지상주차장 주차면 */}
      <g stroke="currentColor" strokeOpacity=".22" strokeWidth="1.2">
        <path d="M172 340H262M172 380H262M172 420H262M172 460H262" />
        <path d="M172 334V466" />
        <path d="M330 340H420M330 380H420M330 420H420M330 460H420" />
        <path d="M420 334V466" />
      </g>
      <g fill="currentColor" opacity=".14">
        <rect x="178" y="347" width="76" height="25" rx="3" />
        <rect x="178" y="427" width="76" height="25" rx="3" />
        <rect x="338" y="387" width="76" height="25" rx="3" />
      </g>

      {/* 놀이터 */}
      <g stroke="currentColor" strokeOpacity=".22" strokeWidth="1.3" fill="none">
        <circle cx="550" cy="372" r="38" />
        <path d="M522 446h56M530 446v-20M570 446v-20" />
      </g>

      {/* 분리수거장 수거함 */}
      <g stroke="currentColor" strokeOpacity=".24" strokeWidth="1.3" fill="currentColor" fillOpacity=".08">
        <rect x="684" y="356" width="36" height="60" rx="5" />
        <rect x="728" y="356" width="36" height="60" rx="5" />
        <rect x="772" y="356" width="36" height="60" rx="5" />
        <rect x="816" y="356" width="36" height="60" rx="5" />
      </g>

      <g className="maplbl" textAnchor="middle">
        <text x="257" y="130">101동</text>
        <text x="507" y="130">102동</text>
        <text x="757" y="130">103동</text>
        <text x="295" y="310">지상주차장</text>
        <text x="550" y="310">놀이터</text>
        <text x="762" y="310">분리수거장</text>
        <text x="257" y="662">104동</text>
        <text x="507" y="662">커뮤니티센터</text>
        <text x="757" y="650">지하주차장 진입</text>
        <text x="757" y="674">지하 1~2층</text>
      </g>

      {/* 순찰 경로 — 잔여 점선 / 완료 실선 */}
      <path
        d="M95 800 L95 230 L960 230 L960 800 Z"
        fill="none" stroke="var(--graphic)" strokeOpacity=".24" strokeWidth="3.4"
        strokeLinecap="round" strokeLinejoin="round" strokeDasharray="10 9"
      />
      <path
        d="M95 800 L95 230 L960 230 L960 340"
        fill="none" stroke="var(--graphic)" strokeWidth="6" strokeLinecap="round" strokeLinejoin="round"
      />

      <g className="station">
        <rect x="150" y="816" width="112" height="34" rx="10" />
        <text x="206" y="838">경비실 · 충전소</text>
      </g>

      {/* 웨이포인트 12개 — 완료 채운 원 / 미완료 빈 원 */}
      <g className="wp">
        <g><circle cx="95" cy="800" r="7" /><text x="130" y="805" textAnchor="start">1번</text></g>
        <g><circle cx="95" cy="515" r="7" /><text x="130" y="520" textAnchor="start">2번</text></g>
        <g><circle cx="95" cy="230" r="7" /><text x="130" y="213" textAnchor="start">3번</text></g>
        <g><circle cx="300" cy="230" r="7" /><text x="300" y="213">4번 · 101동</text></g>
        <g><circle cx="550" cy="230" r="7" /><text x="550" y="213">5번 · 102동</text></g>
        <g><circle cx="790" cy="230" r="7" /><text x="790" y="213">6번 · 103동</text></g>
        <g><circle cx="960" cy="230" r="7" /><text x="924" y="213" textAnchor="end">7번</text></g>
        <g className="pend"><circle cx="960" cy="515" r="7" /><text x="924" y="520" textAnchor="end">8번</text></g>
        <g className="pend"><circle cx="960" cy="800" r="7" /><text x="924" y="805" textAnchor="end">9번</text></g>
        <g className="pend"><circle cx="760" cy="800" r="7" /><text x="760" y="784">10번 · 지하주차장</text></g>
        <g className="pend"><circle cx="520" cy="800" r="7" /><text x="520" y="784">11번 · 커뮤니티</text></g>
        <g className="pend"><circle cx="300" cy="800" r="7" /><text x="300" y="784">12번 · 104동</text></g>
      </g>

      {/* 긴급 마커 — 긴급 이벤트가 있을 때만 */}
      {urgent && (
        <g className="alertpt">
          <circle className="ping2" cx="884" cy="452" r="12" fill="none" stroke="var(--urgent)" strokeWidth="2.4" />
          <circle cx="884" cy="452" r="8" fill="var(--urgent)" />
          <text x="876" y="428" textAnchor="end">{urgent.label}</text>
        </g>
      )}

      {/* 로봇 — 헤일로 + 스캔 콘 + 확산 링 */}
      <g className="bot" transform="translate(960,340) rotate(90)">
        <circle r="80" fill="url(#botHalo)" />
        <path d="M0 0 L104 -50 A116 116 0 0 1 104 50 Z" fill="url(#coneMap)" />
        <circle className="ping" r="18" fill="none" stroke="var(--graphic)" strokeWidth="2.6" />
        <circle r="13" fill="var(--graphic)" />
        <circle r="13" fill="none" stroke="#fff" strokeOpacity=".92" strokeWidth="2.8" />
        <circle r="5" fill="#fff" />
      </g>
      <text className="botlbl" x="888" y="346" textAnchor="end">{robotName}</text>

      {/* 축척 · 방위 */}
      <g className="scale">
        <path d="M780 860 H900" stroke="currentColor" strokeOpacity=".45" strokeWidth="2" />
        <path d="M780 854V866M900 854V866" stroke="currentColor" strokeOpacity=".45" strokeWidth="2" />
        <text x="840" y="848">30미터</text>
      </g>
      <g className="compass" transform="translate(962,62)">
        <circle r="17" fill="none" stroke="currentColor" strokeOpacity=".25" strokeWidth="1.4" />
        <path d="M0 -12 L5.5 4 L0 0 L-5.5 4 Z" fill="var(--graphic)" />
        <text y="-22">북</text>
      </g>
    </svg>
  )
}
