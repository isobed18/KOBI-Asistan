import { Component } from 'react'
import { Routes, Route, Navigate, useLocation } from 'react-router-dom'
import Layout from './components/Layout.jsx'
import Overview  from './pages/Overview.jsx'
import Orders    from './pages/Orders.jsx'
import Cargo     from './pages/Cargo.jsx'
import Inventory from './pages/Inventory.jsx'
import Tickets   from './pages/Tickets.jsx'
import Reports        from './pages/Reports.jsx'
import AdminAssistant from './pages/AdminAssistant.jsx'
import Login          from './pages/Login.jsx'
import Onboarding     from './pages/Onboarding.jsx'
import { AuthProvider, useAuth } from './context/AuthContext.jsx'

class ErrorBoundary extends Component {
  constructor(props) {
    super(props)
    this.state = { error: null }
  }
  static getDerivedStateFromError(err) {
    return { error: err?.message || 'Bilinmeyen bir hata oluştu.' }
  }
  render() {
    if (this.state.error) {
      return (
        <div style={{ padding: '40px 24px', maxWidth: 480 }}>
          <div style={{ fontSize: 32, marginBottom: 12 }}>⚠️</div>
          <div style={{ fontWeight: 700, fontSize: 16, marginBottom: 8, color: 'var(--danger)' }}>
            Sayfa Yüklenemedi
          </div>
          <div style={{ fontSize: 13, color: 'var(--text2)', marginBottom: 20, lineHeight: 1.6 }}>
            {this.state.error}
          </div>
          <button
            className="btn btn-primary btn-sm"
            onClick={() => this.setState({ error: null })}
          >
            ↺ Tekrar Dene
          </button>
        </div>
      )
    }
    return this.props.children
  }
}

function RequireAuth({ children }) {
  const { isAuthenticated } = useAuth()
  const location = useLocation()
  if (!isAuthenticated) {
    return <Navigate to="/login" state={{ from: location }} replace />
  }
  return children
}

function AppRoutes() {
  return (
    <Routes>
      <Route path="/login" element={<Login />} />
      <Route path="/register" element={<Onboarding publicMode />} />
      <Route path="/*" element={
        <RequireAuth>
          <Layout>
            <Routes>
              <Route path="/"          element={<ErrorBoundary><Overview /></ErrorBoundary>}  />
              <Route path="/orders"    element={<ErrorBoundary><Orders /></ErrorBoundary>}    />
              <Route path="/cargo"     element={<ErrorBoundary><Cargo /></ErrorBoundary>}     />
              <Route path="/inventory" element={<ErrorBoundary><Inventory /></ErrorBoundary>} />
              <Route path="/tickets"   element={<ErrorBoundary><Tickets /></ErrorBoundary>}   />
              <Route path="/reports"   element={<ErrorBoundary><Reports /></ErrorBoundary>}   />
              <Route path="/assistant" element={<ErrorBoundary><AdminAssistant /></ErrorBoundary>} />
              <Route path="/setup"     element={<ErrorBoundary><Onboarding /></ErrorBoundary>} />
              <Route path="*"          element={<Navigate to="/" replace />} />
            </Routes>
          </Layout>
        </RequireAuth>
      } />
    </Routes>
  )
}

export default function App() {
  return (
    <AuthProvider>
      <AppRoutes />
    </AuthProvider>
  )
}
