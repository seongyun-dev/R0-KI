# 공용 컴포넌트 인벤토리

`src/components/ui`에 프리미티브를 먼저 만들고 화면을 조립한다. 모든 컴포넌트는 토큰만 사용.
props는 `type`으로 명시, `className` 병합은 `cn()`(clsx + tailwind-merge).

## 프리미티브 (`ui/`)
- **Button / Pill** — variant: `accent | dark | light | outline | ghost`, size: `sm | md | lg`, `withArrow?('right'|'up-right')`, `loading?`. 프로토타입의 필 버튼(둥근 + 화살표 뱃지) 스타일.
- **IconButton** — 원형 아이콘 버튼(모달 닫기 등).
- **Card** — `rounded-card bg-white ring-1 ring-line shadow-soft`. `tone='light'|'dark'`(dark=`bg-card text-white`).
- **StatTile** — 큰 수치 + 라벨 + (증감 델타 ▲▼). 숫자 `font-mono tabular`. KPI/통계/히어로 통계용.
- **StatusBadge** — 라벨 문자열 → tone 자동 매핑(아래 표). `[ 완료 ]`처럼 대괄호 스타일 옵션.
- **Tag / Chip** — 태그 칩.
- **Field** — label + control + hint/error. `Input · Textarea · Select · Checkbox`. 인라인 에러/강도표시 지원(회원가입).
- **Modal** — `role=dialog aria-modal`, 백드롭 블러, Esc 닫기, 포커스 트랩, 진입 트랜지션.
- **Drawer** — 우측 슬라이드(로봇 수정 1k).
- **Toast** — "✓ 저장되었습니다" 등.
- **Table / DataTable** — 컬럼 정의 기반. 정렬/빈 상태/로딩 스켈레톤. 우측 "상세 →" 링크 컬럼.
- **Tabs, Dropdown/Select(필터), DateRange, Breadcrumb, Pagination, ProgressBar(스캔 진행률), Stepper(온보딩 ①②③), EmptyState, Spinner/Skeleton.**
- **Eyebrow** — 점 + 라벨(섹션 소제목).

## 레이아웃 (`layout/`)
- **AppShell** — 헤더 + 좌측 사이드바 + 본문. 라우트 `/app/*` 감싸기.
- **Header(app)** — 브랜드 `AI 순찰 시스템` + `관리자 ▾ | 로그아웃`.
- **Sidebar** — Dashboard · 순찰관리 · 이벤트관리 · 로봇관리 · 통계 · 알림 (활성 표시).
- **PageHeader** — 브레드크럼 + 제목 + 우측 액션들.
- **SiteHeader / SiteFooter** — 랜딩용.

## 3D (`robot/`)
- **PatrolRobot** — 랜딩 히어로 R3F 컴포넌트. landing.html 로직 이식.
- **RobotDiagnosticView** — 로봇 상세의 `[LIVE DIAGNOSTICS]` 정면 45° 프리뷰(간단 버전 재사용 가능).

## StatusBadge tone 매핑 (와이어프레임 상태 → 토큰)
| 라벨 | tone |
|---|---|
| 완료 · 이상무 · 정상 · 순찰중 · 온라인 · 활성 | success |
| 진행중 · 확인중 · 수신됨 · SCANNING | info |
| 미처리 · 점검필요 · 주의 | warning |
| 긴급 · 응급상황 · 침입 | danger |
| (기타/기본) | neutral(muted) |

```ts
// 예시 시그니처
type Tone = 'success' | 'info' | 'warning' | 'danger' | 'neutral';
export function StatusBadge({ label, bracket }: { label: string; bracket?: boolean }): JSX.Element;
```
