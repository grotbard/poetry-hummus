import { useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { api } from '../../lib/api'
import {
  ACTION_LABELS,
  COIN_KIND_LABELS,
  dateTime,
  shekels,
  STATUS_LABELS,
  STATUS_STYLES,
} from '../../lib/format'
import type { UserDetail } from '../../lib/types'
import { Chickpea, CoinAmount } from '../../components/Chickpea'

export function MemberDrawer({ userId, onClose }: { userId: number; onClose: () => void }) {
  const queryClient = useQueryClient()
  const [amount, setAmount] = useState('')
  const [reason, setReason] = useState('')

  const { data, isLoading } = useQuery({
    queryKey: ['admin', 'user', userId],
    queryFn: () => api.get<UserDetail>(`/api/admin/users/${userId}`),
  })

  const invalidate = async () => {
    await queryClient.invalidateQueries({ queryKey: ['admin'] })
  }

  const adjust = useMutation({
    mutationFn: () =>
      api.post(`/api/admin/users/${userId}/coins`, {
        amount: Number(amount),
        reason: reason.trim(),
      }),
    onSuccess: async () => {
      setAmount('')
      setReason('')
      await invalidate()
    },
  })

  const toggle = useMutation({
    mutationFn: () => api.post(`/api/admin/users/${userId}/toggle-active`),
    onSuccess: invalidate,
  })

  const user = data?.user

  return (
    <div className="fixed inset-0 z-40 flex" role="dialog" aria-modal="true">
      <button
        className="flex-1 bg-ink/40 backdrop-blur-sm"
        onClick={onClose}
        aria-label="סגירה"
      />
      <div className="h-full w-full max-w-xl overflow-y-auto bg-hummus-light shadow-2xl">
        <header className="sticky top-0 flex items-center gap-3 border-b border-ink/10 bg-hummus-light/95 px-5 py-4 backdrop-blur">
          <h2 className="flex-1 font-display text-lg text-wine">כרטיס חבר</h2>
          <button onClick={onClose} className="btn-ghost !px-3 !py-1 text-sm">
            סגירה
          </button>
        </header>

        {isLoading && <p className="p-5 text-ink/50">טוען…</p>}

        {user && (
          <div className="space-y-5 p-5">
            <section className="card p-5">
              <div className="flex items-center gap-3">
                {user.picture_url ? (
                  <img
                    src={user.picture_url}
                    alt=""
                    className="h-14 w-14 rounded-full object-cover"
                    referrerPolicy="no-referrer"
                  />
                ) : (
                  <div className="grid h-14 w-14 place-items-center rounded-full bg-teal/30 text-lg font-bold text-teal-deep">
                    {(user.full_name || user.email)[0]?.toUpperCase()}
                  </div>
                )}
                <div className="min-w-0 flex-1">
                  <p className="truncate font-bold">{user.full_name || '—'}</p>
                  <p className="truncate text-sm text-ink/55">{user.email}</p>
                  {user.phone && <p className="text-sm text-ink/55">{user.phone}</p>}
                </div>
              </div>

              <dl className="mt-4 grid grid-cols-2 gap-3 border-t border-ink/10 pt-4 text-sm">
                <div>
                  <dt className="text-xs text-ink/50">יתרת מטבעות</dt>
                  <dd className="mt-0.5">
                    <CoinAmount value={user.coin_balance} className="text-wine" />
                  </dd>
                </div>
                <div>
                  <dt className="text-xs text-ink/50">נצבר מאז ומתמיד</dt>
                  <dd className="mt-0.5 font-bold tabular-nums">
                    {user.lifetime_coins_earned.toLocaleString('he-IL')}
                  </dd>
                </div>
                <div>
                  <dt className="text-xs text-ink/50">נרשם</dt>
                  <dd className="mt-0.5">{dateTime(user.created_at)}</dd>
                </div>
                <div>
                  <dt className="text-xs text-ink/50">כניסה אחרונה</dt>
                  <dd className="mt-0.5">
                    {user.last_login_at ? dateTime(user.last_login_at) : '—'}
                  </dd>
                </div>
              </dl>

              <button
                onClick={() => toggle.mutate()}
                disabled={toggle.isPending}
                className="btn-ghost mt-4 w-full !text-sm"
              >
                {user.is_active ? 'חסימת חשבון' : 'הפעלת חשבון'}
              </button>
              {toggle.isError && (
                <p className="mt-2 text-sm text-red-600">{(toggle.error as Error).message}</p>
              )}
            </section>

            <section className="card p-5">
              <h3 className="flex items-center gap-2 text-base text-wine">
                <Chickpea className="h-4 w-4" />
                עדכון מטבעות ידני
              </h3>
              <div className="mt-3 space-y-2">
                <input
                  className="input"
                  type="number"
                  placeholder="כמות (שלילי = חיוב)"
                  value={amount}
                  onChange={(e) => setAmount(e.target.value)}
                />
                <input
                  className="input"
                  placeholder="סיבה (חובה, נשמרת ביומן)"
                  value={reason}
                  onChange={(e) => setReason(e.target.value)}
                />
                <button
                  onClick={() => adjust.mutate()}
                  disabled={!amount || !reason.trim() || adjust.isPending}
                  className="btn-primary w-full !text-sm"
                >
                  {adjust.isPending ? 'מעדכן…' : 'עדכון יתרה'}
                </button>
                {adjust.isError && (
                  <p className="text-sm text-red-600">{(adjust.error as Error).message}</p>
                )}
              </div>
            </section>

            <section>
              <h3 className="mb-2 text-base text-wine">הזמנות ({data.orders.length})</h3>
              <ul className="space-y-2">
                {data.orders.map((order) => (
                  <li key={order.id} className="card px-4 py-3 text-sm">
                    <div className="flex items-center justify-between gap-2">
                      <span className="font-mono text-xs tabular-nums text-ink/55">
                        {order.order_number}
                      </span>
                      <span className={`chip !px-2 !py-0.5 !text-[11px] ${STATUS_STYLES[order.status]}`}>
                        {STATUS_LABELS[order.status]}
                      </span>
                    </div>
                    <div className="mt-1.5 flex items-center justify-between gap-2">
                      <span className="truncate text-xs text-ink/55">
                        {order.items.map((i) => `${i.quantity}×${i.name_snapshot}`).join(', ')}
                      </span>
                      <span className="shrink-0 font-bold text-wine">
                        {shekels(order.total_agorot)}
                      </span>
                    </div>
                  </li>
                ))}
                {data.orders.length === 0 && (
                  <li className="card p-4 text-center text-sm text-ink/50">אין הזמנות</li>
                )}
              </ul>
            </section>

            <section>
              <h3 className="mb-2 text-base text-wine">תנועות מטבעות</h3>
              <ul className="space-y-1.5">
                {data.coin_transactions.map((tx) => (
                  <li
                    key={tx.id}
                    className="card flex items-center justify-between gap-2 px-4 py-2.5 text-sm"
                  >
                    <div className="min-w-0">
                      <p className="truncate">{COIN_KIND_LABELS[tx.kind] ?? tx.kind}</p>
                      <p className="truncate text-xs text-ink/45">
                        {tx.reason || dateTime(tx.created_at)}
                      </p>
                    </div>
                    <CoinAmount
                      value={tx.amount}
                      signed
                      size="sm"
                      className={tx.amount > 0 ? 'text-teal-deep' : 'text-wine'}
                    />
                  </li>
                ))}
                {data.coin_transactions.length === 0 && (
                  <li className="card p-4 text-center text-sm text-ink/50">אין תנועות</li>
                )}
              </ul>
            </section>

            <section>
              <h3 className="mb-2 text-base text-wine">פעילות</h3>
              <ul className="space-y-1.5">
                {data.activity.map((entry) => (
                  <li key={entry.id} className="card px-4 py-2.5 text-sm">
                    <div className="flex items-center justify-between gap-2">
                      <span>{ACTION_LABELS[entry.action] ?? entry.action}</span>
                      <span className="shrink-0 text-xs text-ink/45">
                        {dateTime(entry.created_at)}
                      </span>
                    </div>
                  </li>
                ))}
                {data.activity.length === 0 && (
                  <li className="card p-4 text-center text-sm text-ink/50">אין פעילות</li>
                )}
              </ul>
            </section>
          </div>
        )}
      </div>
    </div>
  )
}
