import { useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { api } from '../../lib/api'
import { dateTime, shekels, STATUS_LABELS, STATUS_STYLES } from '../../lib/format'
import type { Order, OrderStatus, Paginated } from '../../lib/types'
import { CoinAmount } from '../../components/Chickpea'

const FILTERS: { key: OrderStatus | 'all'; label: string }[] = [
  { key: 'all', label: 'הכל' },
  { key: 'pending', label: 'ממתינות' },
  { key: 'preparing', label: 'בהכנה' },
  { key: 'ready', label: 'מוכנות' },
  { key: 'collected', label: 'נאספו' },
  { key: 'cancelled', label: 'בוטלו' },
]

// Which transitions the staff can trigger from each state.
const NEXT: Partial<Record<OrderStatus, { to: OrderStatus; label: string }[]>> = {
  pending: [
    { to: 'preparing', label: 'התחל הכנה' },
    { to: 'cancelled', label: 'בטל' },
  ],
  preparing: [
    { to: 'ready', label: 'מוכנה' },
    { to: 'cancelled', label: 'בטל' },
  ],
  ready: [{ to: 'collected', label: 'נאספה ושולמה' }],
}

export function AdminOrders() {
  const queryClient = useQueryClient()
  const [filter, setFilter] = useState<OrderStatus | 'all'>('all')
  const [page, setPage] = useState(1)

  const { data, isLoading } = useQuery({
    queryKey: ['admin', 'orders', filter, page],
    queryFn: () =>
      api.get<Paginated<Order>>(
        `/api/admin/orders?page=${page}&page_size=25${filter === 'all' ? '' : `&status=${filter}`}`,
      ),
    refetchInterval: 15_000,
  })

  const setStatus = useMutation({
    mutationFn: ({ id, status }: { id: number; status: OrderStatus }) =>
      api.patch<Order>(`/api/admin/orders/${id}/status`, { status }),
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: ['admin'] })
    },
  })

  const pages = data ? Math.max(1, Math.ceil(data.total / data.page_size)) : 1

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap gap-1.5">
        {FILTERS.map((f) => (
          <button
            key={f.key}
            onClick={() => {
              setFilter(f.key)
              setPage(1)
            }}
            className={`rounded-full px-3.5 py-1.5 text-sm font-medium transition ${
              filter === f.key ? 'bg-wine text-hummus-light' : 'bg-white/70 text-ink/65 hover:bg-white'
            }`}
          >
            {f.label}
          </button>
        ))}
      </div>

      {setStatus.isError && (
        <p className="text-sm text-red-600">{(setStatus.error as Error).message}</p>
      )}
      {isLoading && <p className="text-ink/50">טוען…</p>}

      <div className="space-y-2.5">
        {data?.items.map((order) => (
          <article key={order.id} className="card p-4">
            <header className="flex flex-wrap items-center justify-between gap-2">
              <div className="flex items-center gap-3">
                <span className={`chip ${STATUS_STYLES[order.status]}`}>
                  {STATUS_LABELS[order.status]}
                </span>
                <span className="font-mono text-sm text-ink/60">{order.order_number}</span>
              </div>
              <span className="text-xs text-ink/45">{dateTime(order.created_at)}</span>
            </header>

            <ul className="mt-2.5 flex flex-wrap gap-x-4 gap-y-1 text-sm text-ink/70">
              {order.items.map((item) => (
                <li key={item.id}>
                  {item.quantity} × {item.name_snapshot}
                </li>
              ))}
            </ul>

            {order.note && (
              <p className="mt-2 rounded-xl bg-chickpea/15 px-3 py-1.5 text-xs text-wine-dark">
                הערה: {order.note}
              </p>
            )}

            <footer className="mt-3 flex flex-wrap items-center justify-between gap-2 border-t border-ink/10 pt-3">
              <div className="flex flex-wrap items-center gap-3 text-sm">
                <span className="font-bold text-wine">{shekels(order.total_agorot)}</span>
                <span
                  className={`chip !px-2 !py-0.5 !text-[11px] ${
                    order.payment_status === 'paid'
                      ? 'bg-teal/25 text-teal-deep'
                      : 'bg-ink/10 text-ink/60'
                  }`}
                >
                  {order.payment_status === 'paid' ? 'שולם' : 'לא שולם'}
                </span>
                {order.coins_spent > 0 && (
                  <span className="text-xs text-ink/55">
                    מומשו <CoinAmount value={order.coins_spent} size="sm" />
                  </span>
                )}
                {order.coins_earned > 0 && (
                  <span className="text-xs text-teal-deep">
                    נצברו <CoinAmount value={order.coins_earned} size="sm" />
                  </span>
                )}
              </div>
              <div className="flex gap-1.5">
                {(NEXT[order.status] ?? []).map((action) => (
                  <button
                    key={action.to}
                    onClick={() => setStatus.mutate({ id: order.id, status: action.to })}
                    disabled={setStatus.isPending}
                    className={
                      action.to === 'cancelled'
                        ? 'btn-ghost !px-3 !py-1 text-xs !text-red-600'
                        : 'btn-teal !px-3 !py-1 text-xs'
                    }
                  >
                    {action.label}
                  </button>
                ))}
              </div>
            </footer>
          </article>
        ))}
        {data?.items.length === 0 && (
          <div className="card p-6 text-center text-ink/55">אין הזמנות בסטטוס הזה</div>
        )}
      </div>

      {pages > 1 && (
        <div className="flex items-center justify-center gap-3 text-sm">
          <button
            onClick={() => setPage((p) => Math.max(1, p - 1))}
            disabled={page === 1}
            className="btn-ghost !px-3 !py-1"
          >
            הקודם
          </button>
          <span className="text-ink/55">
            {page} / {pages}
          </span>
          <button
            onClick={() => setPage((p) => Math.min(pages, p + 1))}
            disabled={page >= pages}
            className="btn-ghost !px-3 !py-1"
          >
            הבא
          </button>
        </div>
      )}
    </div>
  )
}
