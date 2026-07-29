import { Suspense, lazy } from 'react'
import { createBrowserRouter } from 'react-router-dom'
import { AppShell } from './components/layout/AppShell'
import { RequireAuth } from './features/auth/RequireAuth'
import Dashboard from './pages/Dashboard'
import Landing from './pages/Landing'
import Login from './pages/Login'
import Signup from './pages/Signup'
import SignupOnboarding from './pages/SignupOnboarding'
import PatrolList from './pages/PatrolList'
import PatrolDetail from './pages/PatrolDetail'
import EventList from './pages/EventList'
import EventDetail from './pages/EventDetail'
import RobotDetail from './pages/RobotDetail'
import RobotList from './pages/RobotList'
import RobotNew from './pages/RobotNew'
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
      // 로봇관리 (1i 목록 → 1i-r01 상세) — R0KiShell 자체 상단바라 AppShell 밖 독립 렌더
      {
        path: 'robots',
        element: (
          <RequireAuth>
            <RobotList />
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
      {
        // 비로그인 접근 시 /login으로 — 나머지 화면은 기존 셸 유지
        element: (
          <RequireAuth>
            <AppShell />
          </RequireAuth>
        ),
        children: [
      { path: 'robots/new', element: <RobotNew /> },
      {
        path: 'stats',
        element: (
          <Suspense fallback={null}>
            <Stats />
          </Suspense>
        ),
      },
        ],
      },
    ],
  },
  { path: '/dev', element: <DevPreview />, errorElement: <RouteError /> },
  { path: '*', element: <NotFound /> },
])
