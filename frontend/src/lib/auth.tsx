import { createContext, useContext, useEffect, useState, type ReactNode } from 'react'
import { api, ApiError } from './api'
import type { User } from './types'

interface AuthState {
  user: User | null
  loading: boolean
  googleEnabled: boolean
  refresh: () => Promise<void>
  logout: () => Promise<void>
  loginAdmin: (email: string, password: string) => Promise<void>
  loginMember: (identifier: string, password: string) => Promise<void>
}

const AuthContext = createContext<AuthState | null>(null)

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<User | null>(null)
  const [loading, setLoading] = useState(true)
  const [googleEnabled, setGoogleEnabled] = useState(false)

  async function refresh() {
    try {
      setUser(await api.get<User>('/api/auth/me'))
    } catch (err) {
      // A 401 just means "not signed in" — not an error worth surfacing.
      if (!(err instanceof ApiError && err.status === 401)) console.error(err)
      setUser(null)
    }
  }

  useEffect(() => {
    void (async () => {
      await refresh()
      try {
        const cfg = await api.get<{ google_enabled: boolean }>('/api/auth/config')
        setGoogleEnabled(cfg.google_enabled)
      } catch {
        setGoogleEnabled(false)
      }
      setLoading(false)
    })()
  }, [])

  async function logout() {
    await api.post('/api/auth/logout')
    setUser(null)
  }

  async function loginAdmin(email: string, password: string) {
    const u = await api.post<User>('/api/auth/admin/login', { email, password })
    setUser(u)
  }

  async function loginMember(identifier: string, password: string) {
    const u = await api.post<User>('/api/auth/login', { identifier, password })
    setUser(u)
  }

  return (
    <AuthContext.Provider
      value={{
        user,
        loading,
        googleEnabled,
        refresh,
        logout,
        loginAdmin,
        loginMember,
      }}
    >
      {children}
    </AuthContext.Provider>
  )
}

export function useAuth(): AuthState {
  const ctx = useContext(AuthContext)
  if (!ctx) throw new Error('useAuth must be used inside AuthProvider')
  return ctx
}
