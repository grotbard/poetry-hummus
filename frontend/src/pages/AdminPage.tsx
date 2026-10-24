import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { api } from '../lib/api'
import type { AdminStats } from '../lib/types'
import { NavLink } from 'react-router-dom'
import { useAuth } from '../lib/auth'
import { Logo } from '../components/Logo'
import { AdminOverview } from './admin/AdminOverview'
import { AdminMembers } from './admin/AdminMembers'
import { AdminApprovals } from './admin/AdminApprovals'
import { AdminOrders } from './admin/AdminOrders'
import { AdminActivity } from './admin/AdminActivity'
import { AdminMenu } from './admin/AdminMenu'

const TABS = [
  { key: 'overview', label: 'סקירה' },
  { key: 'orders', label: 'הזמנות' },
  { key: 'members', label: 'חברי מועדון' },
  { key: 'approvals', label: 'אישורי הצטרפות' },
  { key: 'activity', label: 'יומן פעילות' },
  { key: 'menu', label: 'תפריט' },
] as const

type TabKey = (typeof TABS)[number]['key']

export function AdminPage() {
  const { user, logout } = useAuth()
  const [tab, setTab] = useState<TabKey>('overview')

  // Surfaces a waiting member without needing the tab open.
  const { data: stats } = useQuery({
    queryKey: ['admin', 'stats'],
    queryFn: () => api.get<AdminStats>('/api/admin/stats'),
    refetchInterval: 30_000,
  })
  const pending = stats?.pending_phone_approvals ?? 0

  return (
    <div className="min-h-screen">
      <header className="sticky top-0 z-20 border-b border-ink/10 bg-wine text-hummus-light">
        <div className="mx-auto flex max-w-6xl items-center gap-3 px-4 py-3">
          <Logo className="h-10 w-10 shrink-0" />
          <div className="min-w-0 flex-1">
            <h1 className="font-display text-lg leading-tight">ניהול המועדון</h1>
            <p className="truncate text-xs opacity-70">{user?.email}</p>
          </div>
          <NavLink to="/" className="rounded-full bg-white/15 px-3 py-1.5 text-sm hover:bg-white/25">
            לאפליקציה
          </NavLink>
          <button onClick={logout} className="text-sm opacity-80 hover:opacity-100">
            יציאה
          </button>
        </div>
        <nav className="mx-auto flex max-w-6xl gap-1 overflow-x-auto px-2 pb-2">
          {TABS.map((t) => (
            <button
              key={t.key}
              onClick={() => setTab(t.key)}
              className={`shrink-0 rounded-full px-4 py-1.5 text-sm font-medium transition ${
                tab === t.key ? 'bg-hummus-light text-wine' : 'text-hummus-light/70 hover:bg-white/10'
              }`}
            >
              {t.label}
              {t.key === 'approvals' && pending > 0 && (
                <span
                  className="mr-1.5 inline-flex h-5 min-w-5 items-center justify-center
                             rounded-full bg-chickpea px-1.5 text-xs font-bold text-wine-dark"
                >
                  {pending}
                </span>
              )}
            </button>
          ))}
        </nav>
      </header>

      <main className="mx-auto max-w-6xl px-4 py-6">
        {tab === 'overview' && <AdminOverview />}
        {tab === 'orders' && <AdminOrders />}
        {tab === 'members' && <AdminMembers />}
        {tab === 'approvals' && <AdminApprovals />}
        {tab === 'activity' && <AdminActivity />}
        {tab === 'menu' && <AdminMenu />}
      </main>
    </div>
  )
}
