import { Suspense, lazy } from 'react'
import { createBrowserRouter } from 'react-router-dom'
import { RequireAuth } from './features/auth/RequireAuth'
import Dashboard from './pages/Dashboard'
import Landing from './pages/Landing'
import Login from './pages/Login'
import SignupOnboarding from './pages/SignupOnboarding'
import PatrolList from './pages/PatrolList'
import PatrolDetail from './pages/PatrolDetail'
import EventList from './pages/EventList'
import EventDetail from './pages/EventDetail'
import RobotDetail from './pages/RobotDetail'
import RobotList from './pages/RobotList'
import RobotNew from './pages/RobotNew'
import NotificationList from './pages/NotificationList'
import NotificationDetail from './pages/NotificationDetail'
import MapFull from './pages/MapFull'
import NotFound from './pages/NotFound'
import RouteError from './pages/RouteError'
import DevPreview from './pages/DevPreview'

// 통계는 차트 라이브러리(recharts)를 쓰므로 청크 분리
const Stats = lazy(() => import('./pages/Stats'))

// CLAUDE.md §6 라우트 매핑
export const router = createBrowserRouter([
  { path: '/', element: <Landing />, errorElement: <RouteError /> },
  { path: '/login', element: <Login />, errorElement: <RouteError /> },
  // { path: '/signup', element: <Signup />, errorElement: <RouteError /> },
  { path: '/signup/onboarding', element: <SignupOnboarding />, errorElement: <RouteError /> },
  // 지도 확대 보기 (1h) — 지도 전용 풀스크린이라 AppShell 밖에 둔다
  {
    path: '/app/map',
    element: (
      <RequireAuth>
        <MapFull />
      </RequireAuth>
    ),
    errorElement: <RouteError />,
  },
  {
    path: '/app',
    errorElement: <RouteError />,
    children: [
      // R0-Ki 리디자인 화면 — 자체 상단바 레이아웃(R0KiShell)이라 AppShell 밖 독립 렌더
      {
        index: true,
        element: (
          <RequireAuth>
            <Dashboard />
          </RequireAuth>
        ),
      },
      {
        path: 'patrol',
        element: (
          <RequireAuth>
            <PatrolList />
          </RequireAuth>
        ),
      },
      {
        path: 'patrol/:id',
        element: (
          <RequireAuth>
            <PatrolDetail />
          </RequireAuth>
        ),
      },
      {
        path: 'events',
        element: (
          <RequireAuth>
            <EventList />
          </RequireAuth>
        ),
      },
      {
        path: 'events/:id',
        element: (
          <RequireAuth>
            <EventDetail />
          </RequireAuth>
        ),
      },
      // 알림 기록 (목록 → 상세) — 상단바 알림 버튼 목적지
      {
        path: 'notifications',
        element: (
          <RequireAuth>
            <NotificationList />
          </RequireAuth>
        ),
      },
      {
        path: 'notifications/:id',
        element: (
          <RequireAuth>
            <NotificationDetail />
          </RequireAuth>
        ),
      },
      // 로봇관리 (1i 목록 → 1j 등록 → 1i-r01 상세) — 모두 R0KiShell 자체 상단바
      {
        path: 'robots',
        element: (
          <RequireAuth>
            <RobotList />
          </RequireAuth>
        ),
      },
      {
        path: 'robots/new',
        element: (
          <RequireAuth>
            <RobotNew />
          </RequireAuth>
        ),
      },
      {
        path: 'robots/:id',
        element: (
          <RequireAuth>
            <RobotDetail />
          </RequireAuth>
        ),
      },
      // 통계 — R0KiShell 자체 상단바라 AppShell 밖 독립 렌더 (recharts 청크 지연 로드)
      {
        path: 'stats',
        element: (
          <RequireAuth>
            <Suspense fallback={null}>
              <Stats />
            </Suspense>
          </RequireAuth>
        ),
      },
    ],
  },
  { path: '/dev', element: <DevPreview />, errorElement: <RouteError /> },
  { path: '*', element: <NotFound /> },
])
