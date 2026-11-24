import { Navigate, Outlet, useLocation } from 'react-router-dom'
import { Loader2 } from 'lucide-react'
import { useAuth } from '../../auth/AuthContext'
import { AppSidebar } from './AppSidebar'
import { DeadlineBell, DeadlineProvider, useDeadlines } from './DeadlineBell'

// Screens with a PageHeader show the bell in their header, left of the actions.
const HEADER_BELL_ROUTES = ['/app/overview', '/app/bids', '/app/dashboard']

/** Desktop bell for screens without a PageHeader: top-right of the workspace. */
function FloatingBell() {
  const deadlines = useDeadlines()
  return (
    <div className="hidden lg:block fixed top-3 right-5 z-30">
      <DeadlineBell state={deadlines} align="right" light />
    </div>
  )
}

export function AppLayout() {
  const { user, loading } = useAuth()
  const location = useLocation()

  if (loading) {
    return (
      <div className="min-h-screen bg-canvas flex items-center justify-center">
        <Loader2 className="w-6 h-6 animate-spin text-accent" />
      </div>
    )
  }
  if (!user) {
    return <Navigate to="/login" state={{ from: location }} replace />
  }
  if (!user.email_verified) {
    return <Navigate to="/verify-email" replace />
  }
  // Dark rail, light workspace. The rail is navigation and identity; the
  // content area stays near-white so dense tables and figures read cleanly.
  return (
    <DeadlineProvider>
      <div className="min-h-screen bg-canvas">
        <AppSidebar />
        <div className="lg:pl-rail">
          {!HEADER_BELL_ROUTES.includes(location.pathname) && <FloatingBell />}
          <Outlet />
        </div>
      </div>
    </DeadlineProvider>
  )
}
