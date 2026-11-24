import type { ReactNode } from 'react'
import { BrowserRouter, Routes, Route, Navigate, useLocation } from 'react-router-dom'
import { AuthProvider } from './auth/AuthContext'
import { AppLayout } from './components/layout/AppLayout'
import { ErrorBoundary } from './components/ErrorBoundary'
import { ThemeProvider } from './theme/ThemeContext'

// Sign-in pages
import { Login } from './pages/auth/Login'
import { Signup } from './pages/auth/Signup'
import { VerifyEmail } from './pages/auth/VerifyEmail'
import { NotFound } from './pages/NotFound'
import { AdminUsers } from './pages/admin/AdminUsers'

// Authenticated dashboard pages
import { Overview } from './pages/Overview'
import { DocumentVault } from './pages/DocumentVault'
import { TenderAnalysis } from './pages/TenderAnalysis'
import { RoadmapAnalysis } from './pages/RoadmapAnalysis'
import { BidTracker } from './pages/BidTracker'
import { CompanyProfile } from './pages/CompanyProfile'
import { BidRoom } from './bidroom/BidRoom'
import { TenderHistoryAll } from './pages/TenderHistoryAll'

/**
 * The analysis pages restore their job once on mount, so opening another
 * tender/job from the sidebar or history panel must remount them.
 *
 * Keyed on react-router's location.key rather than location.search: every
 * router navigation (including a click on the URL already shown) gets a new
 * key, while the pages' own window.history.replaceState calls — used to put
 * ?tender=&job= in the address bar mid-run — bypass the router entirely and
 * never change the key, so they cannot remount the page and drop a live run.
 * Keying on search would also miss navigations whose target happens to equal
 * the router's (stale) search, e.g. "New analysis" after an earlier ?new=1.
 */
function RemountOnNavigate({ children }: { children: ReactNode }) {
  const { key } = useLocation()
  return <div key={key}>{children}</div>
}

export default function App() {
  return (
    <ErrorBoundary>
      <ThemeProvider>
      <AuthProvider>
        <BrowserRouter>
          <Routes>
            <Route path="/" element={<Navigate to="/app/overview" replace />} />

            {/* Auth pages — own full-page layout */}
            <Route path="/login" element={<Login />} />
            <Route path="/signup" element={<Signup />} />
            <Route path="/verify-email" element={<VerifyEmail />} />

            {/* The Bid Room — full-viewport chat workspace (its own top bar). */}
            <Route path="/bidroom" element={<BidRoom />} />

            {/* Authenticated dashboard */}
            <Route path="/app" element={<AppLayout />}>
              <Route index element={<Navigate to="/app/overview" replace />} />
              <Route path="overview" element={<Overview />} />
              {/* The pixel-office concept is incomplete. Keep it hidden and use
                  the Bid Room inside the standard dashboard shell instead. */}
              <Route path="dashboard" element={<BidRoom embedded />} />
              <Route path="office" element={<Navigate to="/app/dashboard" replace />} />
              <Route path="bid" element={<RemountOnNavigate><TenderAnalysis /></RemountOnNavigate>} />
              <Route path="analysis" element={<RemountOnNavigate><RoadmapAnalysis /></RemountOnNavigate>} />
              <Route path="history" element={<TenderHistoryAll />} />
              <Route path="bids" element={<BidTracker />} />
              <Route path="vault" element={<DocumentVault />} />
              <Route path="profile" element={<CompanyProfile />} />
              <Route path="admin/users" element={<AdminUsers />} />
            </Route>

            {/* 404 fallback */}
            <Route path="*" element={<NotFound />} />
          </Routes>
        </BrowserRouter>
      </AuthProvider>
      </ThemeProvider>
    </ErrorBoundary>
  )
}
