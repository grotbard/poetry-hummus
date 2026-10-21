import { Navigate, Route, Routes } from 'react-router-dom'
import { Layout } from './components/Layout'
import { useAuth } from './lib/auth'
import { LoginPage } from './pages/LoginPage'
import { MenuPage } from './pages/MenuPage'
import { OrdersPage } from './pages/OrdersPage'
import { CoinsPage } from './pages/CoinsPage'
import { RewardsPage } from './pages/RewardsPage'
import { AdminPage } from './pages/AdminPage'
import { Logo } from './components/Logo'

function Splash() {
  return (
    <div className="min-h-screen grid place-items-center">
      <div className="flex flex-col items-center gap-3">
        <Logo className="w-20 h-20 animate-pulse" />
        <p className="text-ink/50 text-sm">טוען…</p>
      </div>
    </div>
  )
}

function RequireAuth({ children, admin = false }: { children: JSX.Element; admin?: boolean }) {
  const { user, loading } = useAuth()
  if (loading) return <Splash />
  if (!user) return <Navigate to="/login" replace />
  if (admin && user.role !== 'admin') return <Navigate to="/" replace />
  return children
}

export function App() {
  return (
    <Routes>
      <Route path="/login" element={<LoginPage />} />
      <Route
        element={
          <RequireAuth>
            <Layout />
          </RequireAuth>
        }
      >
        <Route path="/" element={<MenuPage />} />
        <Route path="/orders" element={<OrdersPage />} />
        <Route path="/coins" element={<CoinsPage />} />
        <Route path="/rewards" element={<RewardsPage />} />
      </Route>
      <Route
        path="/admin"
        element={
          <RequireAuth admin>
            <AdminPage />
          </RequireAuth>
        }
      />
      <Route path="*" element={<Navigate to="/" replace />} />
    </Routes>
  )
}
