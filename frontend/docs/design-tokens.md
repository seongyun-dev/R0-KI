# 디자인 토큰 레퍼런스

원천: `src/styles/tokens.css` (CSS 변수) = `tailwind.config.js` (동일 값). **임의 hex 금지.**

## 색 (Tailwind 유틸)
| 용도 | 토큰 | 값 | 예시 유틸 |
|---|---|---|---|
| 페이지 배경 | bg | #ffffff | `bg-bg` |
| 본문 텍스트 | fg | #111111 | `text-fg` |
| 딥 블랙(오버레이/푸터) | ink | #0a0a0a | `bg-ink` |
| 대시보드 딥 카드 | card | #0d0d10 | `bg-card` |
| 연한 채움 | surface / surface-2 | #f2f1ef / #e7e5e1 | `bg-surface` |
| 헤어라인 | line | #e6e5e2 | `border-line` |
| 흐린 텍스트 | muted / subtle | #8a8a8a / #b6b6b6 | `text-muted` |
| **액센트(오렌지)** | accent | #e0532a | `bg-accent text-white` |
| 액센트 밝게/진하게/연하게 | accent-light / deep / soft | #ff6a3d / #b8431e / #f6d9cb | `bg-accent-soft` |
| 성공·정상·순찰중 | success (+soft) | #16a34a | `text-success bg-success-soft` |
| 진행중·확인중·경로 | info (+soft) | #2563eb | |
| 미처리·점검필요·주의 | warning (+soft) | #d97706 | |
| 긴급·응급·침입 | danger (+soft) | #e5484d | |
| 라이브 점 | online | #22c55e | |

## 타이포
- 본문: **Pretendard** (`font-sans`). 가중치 400/500/600/700.
- 숫자·시간·수치·ID: `font-mono` + `.tabular` (예: `class="font-mono tabular"`).
- 대략 스케일: 히어로 H1 `text-5xl~7xl`, 섹션 H2 `text-3xl~5xl`, 카드 제목 `text-xl~2xl`, 본문 `text-sm~base`, 캡션/라벨 `text-xs`.

## 반경
`rounded-pill`(버튼·칩·뱃지) · `rounded-card`(큰 카드/패널 32px) · `rounded-card-sm`(중간 20px) · `rounded-control`(입력/작은 버튼 14px). 대시보드 표/작은 요소는 `rounded-md`(12) / `rounded-sm`(8).

## 그림자
`shadow-soft`(미세) · `shadow-card`(카드 부양) · `shadow-pop`(모달). 헤어라인 링은 `ring-1 ring-line`.

## 모션
- hover 스프링/진입: `ease-out` (`cubic-bezier(.22,1,.36,1)`), 약 .35s(hover)~.7s(진입).
- hover 리프트·스케일은 **데스크톱만**: `md:hover:...` + pointer 있는 기기. `@media (prefers-reduced-motion)` 시 모션 제거(전역 처리됨).
- 카운트업/리빌은 뷰포트 진입 시 1회.

## 레이아웃
- 페이지 컨테이너: `max-w-shell mx-auto` + 좌우 패딩 `px-5 sm:px-8`.
- 브레이크포인트: sm 640 / md 768 / lg 1024 / xl 1280.
