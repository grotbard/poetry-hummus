import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { api } from '../../lib/api'
import { ACTION_LABELS, dateTime } from '../../lib/format'
import type { ActivityEntry, Paginated } from '../../lib/types'

const ACTIONS = [
  'all',
  'user.registered',
  'user.login',
  'admin.login',
  'order.created',
  'order.status_changed',
  'reward.redeemed',
  'admin.coins_adjusted',
  'admin.user_toggled',
]

export function AdminActivity() {
  const [action, setAction] = useState('all')
  const [days, setDays] = useState(30)
  const [page, setPage] = useState(1)

  const { data, isLoading } = useQuery({
    queryKey: ['admin', 'activity', action, days, page],
    queryFn: () =>
      api.get<Paginated<ActivityEntry>>(
        `/api/admin/activity?days=${days}&page=${page}&page_size=50${
          action === 'all' ? '' : `&action=${encodeURIComponent(action)}`
        }`,
      ),
  })

  const pages = data ? Math.max(1, Math.ceil(data.total / data.page_size)) : 1

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center gap-2">
        <select
          className="input max-w-[14rem]"
          value={action}
          onChange={(e) => {
            setAction(e.target.value)
            setPage(1)
          }}
        >
          {ACTIONS.map((a) => (
            <option key={a} value={a}>
              {a === 'all' ? 'כל הפעולות' : (ACTION_LABELS[a] ?? a)}
            </option>
          ))}
        </select>
        <select
          className="input max-w-[10rem]"
          value={days}
          onChange={(e) => {
            setDays(Number(e.target.value))
            setPage(1)
          }}
        >
          <option value={1}>24 שעות</option>
          <option value={7}>שבוע</option>
          <option value={30}>חודש</option>
          <option value={90}>3 חודשים</option>
          <option value={365}>שנה</option>
        </select>
        {data && <span className="text-sm text-ink/55">{data.total} רשומות</span>}
      </div>

      {isLoading && <p className="text-ink/50">טוען…</p>}

      <ul className="space-y-1.5">
        {data?.items.map((entry) => (
          <li key={entry.id} className="card flex items-start gap-3 px-4 py-3 text-sm">
            <span className="mt-1.5 h-2 w-2 shrink-0 rounded-full bg-teal-deep" />
            <div className="min-w-0 flex-1">
              <p className="font-medium">{ACTION_LABELS[entry.action] ?? entry.action}</p>
              {Object.keys(entry.details).length > 0 && (
                <p className="mt-0.5 break-words text-xs text-ink/50">
                  {Object.entries(entry.details)
                    .map(([k, v]) => `${k}: ${String(v)}`)
                    .join(' · ')}
                </p>
              )}
            </div>
            <div className="shrink-0 text-right text-xs text-ink/45">
              <p>{dateTime(entry.created_at)}</p>
              {entry.user_id && <p className="mt-0.5">חבר #{entry.user_id}</p>}
            </div>
          </li>
        ))}
        {data?.items.length === 0 && (
          <li className="card p-6 text-center text-ink/55">אין פעילות בטווח הזה</li>
        )}
      </ul>

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
