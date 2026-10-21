import { useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { api } from '../lib/api'
import { useAuth } from '../lib/auth'
import { dateTime, shekels, STATUS_LABELS, STATUS_STYLES } from '../lib/format'
import type { CoinRules, Order } from '../lib/types'
import { CoinAmount } from '../components/Chickpea'
import { FeedbackCard } from '../components/FeedbackCard'

export function OrdersPage() {
  const queryClient = useQueryClient()
  const { refresh } = useAuth()

  const { data: orders = [], isLoading } = useQuery({
    queryKey: ['orders'],
    queryFn: () => api.get<Order[]>('/api/orders'),
    // Keep the status fresh while the kitchen works.
    refetchInterval: 20_000,
  })
  const [justRated, setJustRated] = useState<Set<number>>(new Set())

  const { data: rules } = useQuery({
    queryKey: ['coin-rules'],
    queryFn: () => api.get<CoinRules>('/api/coins/rules'),
  })

  /** Feedback still earns coins for a limited time after collection. */
  function windowOpen(order: Order): boolean {
    if (!order.collected_at) return false
    const hours = rules?.feedback_window_hours ?? 10
    const deadline = new Date(order.collected_at).getTime() + hours * 3_600_000
    return Date.now() <= deadline
  }

  const cancel = useMutation({
    mutationFn: (id: number) => api.post<Order>(`/api/orders/${id}/cancel`),
    onSuccess: async () => {
      await refresh()
      await queryClient.invalidateQueries({ queryKey: ['orders'] })
      await queryClient.invalidateQueries({ queryKey: ['coins'] })
    },
  })

  if (isLoading) return <p className="text-ink/50">טוען הזמנות…</p>
  if (orders.length === 0)
    return (
      <div className="card p-8 text-center">
        <p className="text-ink/60">עוד לא הזמנתם דבר. הגיע הזמן לחומוס.</p>
      </div>
    )

  return (
    <div className="space-y-3">
      {orders.map((order) => (
        <article key={order.id} className="card p-5">
          <header className="flex flex-wrap items-center justify-between gap-2">
            <div>
              <h3 className="font-mono text-sm text-ink/60">{order.order_number}</h3>
              <p className="text-xs text-ink/45">{dateTime(order.created_at)}</p>
            </div>
            <span className={`chip ${STATUS_STYLES[order.status]}`}>
              {STATUS_LABELS[order.status]}
            </span>
          </header>

          <ul className="mt-3 space-y-1 text-sm">
            {order.items.map((item) => (
              <li key={item.id} className="flex justify-between gap-2">
                <span className="truncate">
                  {item.quantity} × {item.name_snapshot}
                  {item.eggs > 0 && (
                    <span className="text-ink/50"> · 🥚 ×{item.eggs}</span>
                  )}
                </span>
                <span className="tabular-nums shrink-0 text-ink/60">
                  {shekels(item.line_total_agorot)}
                </span>
              </li>
            ))}
          </ul>

          {order.note && (
            <p className="mt-2 rounded-xl bg-hummus/40 px-3 py-2 text-xs text-ink/70">
              {order.note}
            </p>
          )}

          <footer className="mt-3 flex flex-wrap items-center justify-between gap-3 border-t border-ink/10 pt-3">
            <div className="flex flex-wrap items-center gap-3 text-sm">
              <span className="font-bold text-wine">{shekels(order.total_agorot)}</span>
              {order.coins_spent > 0 && (
                <span className="text-ink/55">
                  מומשו <CoinAmount value={order.coins_spent} size="sm" />
                </span>
              )}
              {order.coins_earned > 0 && (
                <span className="text-teal-deep">
                  נצברו <CoinAmount value={order.coins_earned} size="sm" />
                </span>
              )}
            </div>
            {order.status === 'pending' && (
              <button
                onClick={() => cancel.mutate(order.id)}
                disabled={cancel.isPending}
                className="text-sm text-red-600 hover:underline"
              >
                ביטול הזמנה
              </button>
            )}
          </footer>

          {order.status === 'collected' &&
            (!order.feedback_at || justRated.has(order.id)) &&
            windowOpen(order) && (
              <FeedbackCard
                order={order}
                onRated={() => setJustRated((prev) => new Set(prev).add(order.id))}
              />
            )}
        </article>
      ))}
      {cancel.isError && (
        <p className="text-sm text-red-600">{(cancel.error as Error).message}</p>
      )}
    </div>
  )
}
