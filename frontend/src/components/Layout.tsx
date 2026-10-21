import { NavLink, Outlet, useNavigate } from 'react-router-dom'
import { useAuth } from '../lib/auth'
import { CoinAmount } from './Chickpea'
import { Logo } from './Logo'

const memberTabs = [
  { to: '/', label: 'תפריט' },
  { to: '/orders', label: 'ההזמנות שלי' },
  { to: '/coins', label: 'מטבעות משורר' },
  { to: '/rewards', label: 'הטבות' },
]

export function Layout() {
  const { user, logout } = useAuth()
  const navigate = useNavigate()

  async function handleLogout() {
    await logout()
    navigate('/login')
  }

  return (
    <div className="min-h-screen flex flex-col">
      <header className="sticky top-0 z-20 bg-hummus-light/85 backdrop-blur border-b border-ink/10">
        <div className="mx-auto max-w-5xl px-4 py-3 flex items-center gap-3">
          <Logo className="w-11 h-11 shrink-0" />
          <div className="min-w-0 flex-1">
            <h1 className="font-display text-lg sm:text-xl leading-tight text-wine">
              חומוס המשורר
            </h1>
            <p className="text-xs text-ink/55 truncate">מועדון הלקוחות</p>
          </div>

          {user && (
            <div className="flex items-center gap-2 sm:gap-3">
              <div className="rounded-full bg-wine px-3 py-1.5 text-hummus-light">
                <CoinAmount value={user.coin_balance} size="sm" />
              </div>
              {user.role === 'admin' && (
                <NavLink to="/admin" className="btn-ghost !px-3 !py-1.5 text-sm">
                  ניהול
                </NavLink>
              )}
              <button onClick={handleLogout} className="text-sm text-ink/60 hover:text-wine">
                יציאה
              </button>
            </div>
          )}
        </div>

        {user && (
          <nav className="mx-auto max-w-5xl px-2 pb-2 flex gap-1 overflow-x-auto">
            {memberTabs.map((tab) => (
              <NavLink
                key={tab.to}
                to={tab.to}
                end={tab.to === '/'}
                className={({ isActive }) =>
                  `shrink-0 rounded-full px-4 py-1.5 text-sm font-medium transition ${
                    isActive
                      ? 'bg-teal-deep text-white shadow'
                      : 'text-ink/65 hover:bg-white/70'
                  }`
                }
              >
                {tab.label}
              </NavLink>
            ))}
          </nav>
        )}
      </header>

      <main className="mx-auto w-full max-w-5xl flex-1 px-4 py-6">
        <Outlet />
      </main>

      <footer className="mx-auto max-w-5xl w-full px-4 py-6 text-center text-xs text-ink/45">
        חומוס המשורר · 
        <a
          href="https://www.google.com/maps/search/?api=1&query=%D7%97%D7%95%D7%9E%D7%95%D7%A1+%D7%94%D7%9E%D7%A9%D7%95%D7%A8%D7%A8+%D7%90%D7%91%D7%9F+%D7%92%D7%91%D7%99%D7%A8%D7%95%D7%9C+8+%D7%AA%D7%9C+%D7%90%D7%91%D7%99%D7%91"
          target="_blank"
          rel="noreferrer"
          className="underline decoration-dotted underline-offset-2 hover:text-wine"
        >
          אבן גבירול 8, תל אביב-יפו
        </a>{' '}
        · <a href="tel:036878635" className="hover:text-wine">03-6878635</a>
      </footer>
    </div>
  )
}
