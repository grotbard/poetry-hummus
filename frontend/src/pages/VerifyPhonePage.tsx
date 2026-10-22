import { useAuth } from '../lib/auth'
import { PhoneVerify } from '../components/PhoneVerify'
import { Logo } from '../components/Logo'

/**
 * Blocking step for a member who signed in without a verified number.
 * The restaurant needs a reachable phone on every order.
 */
export function VerifyPhonePage() {
  const { refresh, logout } = useAuth()

  return (
    <div className="grid min-h-screen place-items-center px-4 py-10">
      <div className="w-full max-w-md">
        <div className="mb-6 flex flex-col items-center gap-3 text-center">
          <Logo className="h-20 w-20" />
          <div>
            <h1 className="font-display text-2xl text-wine">אימות מספר טלפון</h1>
            <p className="mt-1 text-sm text-ink/60">
              נותר שלב אחד — נשתמש במספר כדי לעדכן אותך על ההזמנה
            </p>
          </div>
        </div>

        <div className="card p-6">
          <PhoneVerify mode="attach" onVerified={() => void refresh()} />
        </div>

        <button
          onClick={logout}
          className="mt-5 w-full text-sm text-ink/45 hover:text-wine"
        >
          יציאה
        </button>
      </div>
    </div>
  )
}
