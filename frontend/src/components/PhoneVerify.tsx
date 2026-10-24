import { useEffect, useState } from 'react'
import { api } from '../lib/api'
import type { PhoneCodeSent, User } from '../lib/types'

type Step = 'phone' | 'code'

/**
 * Two-step phone verification, used both for signing up and for adding a
 * number to an account that came in through Google.
 */
export function PhoneVerify({
  mode,
  onVerified,
}: {
  mode: 'signup' | 'attach'
  onVerified: (user: User) => void
}) {
  const [step, setStep] = useState<Step>('phone')
  const [phone, setPhone] = useState('')
  const [code, setCode] = useState('')
  const [email, setEmail] = useState('')
  const [name, setName] = useState('')
  const [password, setPassword] = useState('')
  const [devCode, setDevCode] = useState<string | null>(null)
  const [cooldown, setCooldown] = useState(0)
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)
  const [requested, setRequested] = useState(false)

  // Countdown until another code may be requested.
  useEffect(() => {
    if (cooldown <= 0) return
    const timer = setTimeout(() => setCooldown((n) => n - 1), 1000)
    return () => clearTimeout(timer)
  }, [cooldown])

  async function sendCode() {
    setError('')
    setBusy(true)
    try {
      const sent = await api.post<PhoneCodeSent>('/api/auth/phone/request', { phone })
      setPhone(sent.phone)
      setCooldown(sent.resend_in_seconds)
      setDevCode(sent.dev_code)
      setStep('code')
    } catch (e) {
      setError(e instanceof Error ? e.message : 'שליחת הקוד נכשלה')
    } finally {
      setBusy(false)
    }
  }

  /** Give up on the SMS and let an admin confirm the number instead. */
  async function askAdmin() {
    setError('')
    setBusy(true)
    try {
      const ref = (() => {
        try {
          return sessionStorage.getItem('poet_ref')
        } catch {
          return null
        }
      })()
      const user =
        mode === 'signup'
          ? await api.post<User>('/api/auth/phone/request-approval', {
              phone,
              email,
              full_name: name,
              password: password || null,
              ref,
            })
          : await api.post<User>('/api/auth/phone/request-approval-self', { phone })
      setRequested(true)
      onVerified(user)
    } catch (e) {
      setError(e instanceof Error ? e.message : 'הבקשה נכשלה')
    } finally {
      setBusy(false)
    }
  }

  async function submitCode() {
    setError('')
    setBusy(true)
    try {
      const ref =
        mode === 'signup'
          ? (() => {
              try {
                return sessionStorage.getItem('poet_ref')
              } catch {
                return null
              }
            })()
          : null
      const user =
        mode === 'signup'
          ? await api.post<User>('/api/auth/phone/signup', {
              phone,
              code,
              email,
              full_name: name,
              password: password || null,
              ref,
            })
          : await api.post<User>('/api/auth/phone/verify', { phone, code })
      onVerified(user)
    } catch (e) {
      setError(e instanceof Error ? e.message : 'האימות נכשל')
    } finally {
      setBusy(false)
    }
  }

  if (step === 'phone') {
    const detailsNeeded = mode === 'signup'
    const passwordOk = !detailsNeeded || password.length >= 8
    const ready =
      phone.trim().length >= 9 &&
      (!detailsNeeded || email.trim().includes('@')) &&
      passwordOk
    return (
      <div className="space-y-3">
        {detailsNeeded && (
          <>
            <input
              className="input"
              placeholder="שם מלא"
              value={name}
              onChange={(e) => setName(e.target.value)}
              autoComplete="name"
            />
            <input
              className="input"
              type="email"
              placeholder="אימייל"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              autoComplete="email"
              dir="ltr"
            />
          </>
        )}
        <input
          className="input"
          type="tel"
          placeholder="מספר טלפון (05X-XXXXXXX)"
          value={phone}
          onChange={(e) => setPhone(e.target.value)}
          autoComplete="tel"
          dir="ltr"
        />
        {detailsNeeded && (
          <>
            <input
              className="input"
              type="password"
              placeholder="סיסמה (8 תווים לפחות)"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              autoComplete="new-password"
              dir="ltr"
            />
            <p className="-mt-1 text-xs text-ink/45">
              עם הסיסמה תוכלו להיכנס בפעם הבאה בלי קוד אימות
            </p>
          </>
        )}
        {error && <p className="text-sm text-red-600">{error}</p>}
        <button
          onClick={sendCode}
          disabled={!ready || busy}
          className="btn-primary w-full"
        >
          {busy ? 'שולח…' : 'שליחת קוד אימות'}
        </button>

        {/* Offered here too, not only after a code fails to arrive: the
            member may already know SMS will not reach them. */}
        <div className="border-t border-ink/10 pt-3">
          <button
            onClick={askAdmin}
            disabled={!ready || busy || requested}
            className="btn-ghost w-full !py-2 text-sm"
          >
            {requested ? 'הבקשה נשלחה ✓' : 'בקשת אישור מנהל'}
          </button>
          <p className="mt-1.5 text-center text-xs text-ink/45">
            מנהל יאשר את המספר ידנית
          </p>
        </div>
      </div>
    )
  }

  return (
    <div className="space-y-3">
      <p className="text-sm text-ink/65">
        שלחנו קוד אימות ל<span dir="ltr">{phone}</span>
      </p>
      {devCode && (
        <p className="rounded-2xl bg-chickpea/20 px-4 py-2 text-sm text-wine-dark">
          מצב פיתוח — הקוד הוא <strong className="font-mono">{devCode}</strong>
        </p>
      )}
      <input
        className="input text-center font-mono text-xl tracking-[0.4em]"
        inputMode="numeric"
        maxLength={6}
        placeholder="______"
        value={code}
        onChange={(e) => setCode(e.target.value.replace(/\D/g, ''))}
        autoComplete="one-time-code"
        dir="ltr"
        autoFocus
      />
      {error && <p className="text-sm text-red-600">{error}</p>}
      <button
        onClick={submitCode}
        disabled={code.length < 4 || busy}
        className="btn-primary w-full"
      >
        {busy ? 'מאמת…' : 'אימות'}
      </button>
      <div className="flex items-center justify-between text-sm">
        <button
          onClick={() => {
            setStep('phone')
            setCode('')
            setError('')
          }}
          className="text-ink/55 hover:text-wine"
        >
          שינוי מספר
        </button>
        <button
          onClick={sendCode}
          disabled={cooldown > 0 || busy}
          className="text-ink/55 hover:text-wine disabled:opacity-40"
        >
          {cooldown > 0 ? `שליחה חוזרת בעוד ${cooldown}` : 'שליחת קוד חדש'}
        </button>
      </div>

      {/* When the SMS never arrives, a human can confirm the number. */}
      <div className="border-t border-ink/10 pt-3">
        <p className="mb-2 text-center text-xs text-ink/45">
          לא קיבלתם את ההודעה?
        </p>
        <button
          onClick={askAdmin}
          disabled={busy || requested}
          className="btn-ghost w-full !py-2 text-sm"
        >
          {requested ? 'הבקשה נשלחה ✓' : 'בקשת אישור מנהל'}
        </button>
      </div>
    </div>
  )
}
