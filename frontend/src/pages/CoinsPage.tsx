import { useQuery } from '@tanstack/react-query'
import { api } from '../lib/api'
import { useAuth } from '../lib/auth'
import { COIN_KIND_LABELS, dateOnly, dateTime } from '../lib/format'
import type { CoinRules, CoinTransaction } from '../lib/types'
import { Chickpea, CoinAmount } from '../components/Chickpea'
import { InviteFriends } from '../components/InviteFriends'

export function CoinsPage() {
  const { user } = useAuth()
  const { data: txs = [], isLoading } = useQuery({
    queryKey: ['coins'],
    queryFn: () => api.get<CoinTransaction[]>('/api/coins/transactions'),
  })
  const { data: rules } = useQuery({
    queryKey: ['coin-rules'],
    queryFn: () => api.get<CoinRules>('/api/coins/rules'),
  })
  // Coins are presented as a standalone currency, so nothing here converts
  // them to shekels; the cart shows the actual discount at checkout.
  const redeemedCount = txs.filter((t) => t.kind === 'redeem').length

  // The next credit to lapse, so the member knows what is time-limited.
  const nextExpiry = txs
    .filter((t) => t.amount > 0 && t.expires_at)
    .map((t) => t.expires_at as string)
    .filter((iso) => new Date(iso) > new Date())
    .sort()[0]

  return (
    <div className="space-y-6">
      <section className="card overflow-hidden">
        <div className="bg-wine px-6 py-8 text-center text-hummus-light">
          <Chickpea className="mx-auto h-14 w-14 coin-pop" />
          <p className="mt-3 text-sm opacity-80">מטבעות משורר שלך</p>
          <p className="mt-1 text-5xl font-black tabular-nums">
            {(user?.coin_balance ?? 0).toLocaleString('he-IL')}
          </p>
        </div>
        {nextExpiry && (
          <p className="bg-chickpea/20 px-4 py-2 text-center text-xs text-wine-dark">
            המטבעות הקרובים לפוג: {dateOnly(nextExpiry)}
          </p>
        )}
        <div className="grid grid-cols-2 divide-x divide-x-reverse divide-ink/10 text-center">
          <div className="px-4 py-4">
            <p className="text-xs text-ink/50">נצבר מאז ההרשמה</p>
            <p className="mt-1 text-xl font-bold tabular-nums text-ink">
              {(user?.lifetime_coins_earned ?? 0).toLocaleString('he-IL')}
            </p>
          </div>
          <div className="px-4 py-4">
            <p className="text-xs text-ink/50">מימושים</p>
            <p className="mt-1 text-xl font-bold text-ink">
              {redeemedCount.toLocaleString('he-IL')}
            </p>
          </div>
        </div>
      </section>

      <InviteFriends />

      <section className="card p-5">
        <h2 className="mb-1 text-lg text-wine">איך זה עובד</h2>
        <ul className="mt-3 space-y-2 text-sm text-ink/70">
          <li className="flex gap-2">
            <Chickpea className="mt-0.5 h-4 w-4 shrink-0" />
            אחרי איסוף ההזמנה דרגו אותה בקצרה — והמטבעות נכנסים ליתרה.
          </li>
          <li className="flex gap-2">
            <Chickpea className="mt-0.5 h-4 w-4 shrink-0" />
            אפשר לממש מטבעות להנחה בהזמנה או להטבות מהמועדון.
          </li>
          <li className="flex gap-2">
            <Chickpea className="mt-0.5 h-4 w-4 shrink-0" />
            ההנחה המדויקת מוצגת בעגלה לפני שליחת ההזמנה.
          </li>
          <li className="flex gap-2">
            <Chickpea className="mt-0.5 h-4 w-4 shrink-0" />
            הזמנה שבוטלה מחזירה את המטבעות שמומשו בה.
          </li>
          {(rules?.coin_expiry_days ?? 0) > 0 && (
            <li className="flex gap-2">
              <Chickpea className="mt-0.5 h-4 w-4 shrink-0" />
              מטבעות תקפים {rules?.coin_expiry_days} ימים מיום הצבירה.
            </li>
          )}
        </ul>
      </section>

      <section>
        <h2 className="mb-3 text-lg text-wine">היסטוריית מטבעות</h2>
        {isLoading && <p className="text-ink/50">טוען…</p>}
        {!isLoading && txs.length === 0 && (
          <div className="card p-6 text-center text-ink/55">אין תנועות עדיין</div>
        )}
        <ul className="space-y-2">
          {txs.map((tx) => (
            <li key={tx.id} className="card flex items-center gap-3 px-4 py-3">
              <div
                className={`grid h-9 w-9 shrink-0 place-items-center rounded-full ${
                  tx.amount > 0 ? 'bg-teal/25' : 'bg-wine/10'
                }`}
              >
                <Chickpea className="h-5 w-5" />
              </div>
              <div className="min-w-0 flex-1">
                <p className="text-sm font-medium">
                  {COIN_KIND_LABELS[tx.kind] ?? tx.kind}
                </p>
                <p className="truncate text-xs text-ink/50">
                  {tx.reason || dateTime(tx.created_at)}
                </p>
              </div>
              <div className="shrink-0 text-right">
                <CoinAmount
                  value={tx.amount}
                  signed
                  size="sm"
                  className={tx.amount > 0 ? 'text-teal-deep' : 'text-wine'}
                />
                <p className="text-[11px] text-ink/40">יתרה: {tx.balance_after}</p>
              </div>
            </li>
          ))}
        </ul>
      </section>
    </div>
  )
}
