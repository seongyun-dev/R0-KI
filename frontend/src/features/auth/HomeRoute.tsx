import { Navigate } from 'react-router-dom'
import Landing from '../../pages/Landing'
import { useAuthStore } from './useAuthStore'

export function HomeRoute() {
  const isAuthenticated = useAuthStore((state) => state.isAuthenticated)
  const accessToken = useAuthStore((state) => state.accessToken)
  const accessTokenExpiresAt = useAuthStore((state) => state.accessTokenExpiresAt)
  const hasValidToken =
    isAuthenticated &&
    Boolean(accessToken) &&
    accessTokenExpiresAt != null &&
    accessTokenExpiresAt > Date.now()

  return hasValidToken ? <Navigate to="/app" replace /> : <Landing />
}
