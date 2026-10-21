import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { api } from '../../lib/api'
import { dateOnly, shekels } from '../../lib/format'
import type { AdminUserRow, Paginated } from '../../lib/types'
import { CoinAmount } from '../../components/Chickpea'
import { MemberDrawer } from './MemberDrawer'

export function AdminMembers() {
  const [q, setQ] = useState('')
  const [page, setPage] = useState(1)
  const [selected, setSelected] = useState<number | null>(null)

  const { data, isLoading } = useQuery({
    queryKey: ['admin', 'users', q, page],
    queryFn: () =>
      api.get<Paginated<AdminUserRow>>(
        `/api/admin/users?page=${page}&page_size=25${q ? `&q=${encodeURIComponent(q)}` : ''}`,
      ),
  })

  const pages = data ? Math.max(1, Math.ceil(data.total / data.page_size)) : 1

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center gap-3">
        <input
          className="input max-w-xs"
          placeholder="חיפוש לפי שם או אימייל…"
          value={q}
          onChange={(e) => {
            setQ(e.target.value)
            setPage(1)
          }}
        />
        {data && <span className="text-sm text-ink/55">{data.total} חברים</span>}
      </div>

      {isLoading && <p className="text-ink/50">טוען…</p>}

      <div className="card overflow-x-auto">
        <table className="w-full min-w-[46rem] text-sm">
          <thead className="border-b border-ink/10 text-right text-xs text-ink/50">
            <tr>
              <th className="px-4 py-3 font-medium">חבר</th>
              <th className="px-4 py-3 font-medium">מטבעות</th>
              <th className="px-4 py-3 font-medium">הזמנות</th>
              <th className="px-4 py-3 font-medium">סך רכישות</th>
              <th className="px-4 py-3 font-medium">נרשם</th>
              <th className="px-4 py-3 font-medium">סטטוס</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-ink/[0.07]">
            {data?.items.map((row) => (
              <tr
                key={row.id}
                onClick={() => setSelected(row.id)}
                className="cursor-pointer transition hover:bg-hummus/25"
              >
                <td className="px-4 py-3">
                  <div className="flex items-center gap-2.5">
                    {row.picture_url ? (
                      <img
                        src={row.picture_url}
                        alt=""
                        className="h-8 w-8 rounded-full object-cover"
                        referrerPolicy="no-referrer"
                      />
                    ) : (
                      <div className="grid h-8 w-8 place-items-center rounded-full bg-teal/30 text-xs font-bold text-teal-deep">
                        {(row.full_name || row.email)[0]?.toUpperCase()}
                      </div>
                    )}
                    <div className="min-w-0">
                      <p className="truncate font-medium">{row.full_name || '—'}</p>
                      <p className="truncate text-xs text-ink/50">{row.email}</p>
                    </div>
                    {row.role === 'admin' && (
                      <span className="chip bg-wine/10 text-wine !px-2 !py-0.5 !text-[10px]">
                        מנהל
                      </span>
                    )}
                  </div>
                </td>
                <td className="px-4 py-3">
                  <CoinAmount value={row.coin_balance} size="sm" className="text-wine" />
                </td>
                <td className="px-4 py-3 tabular-nums">{row.order_count}</td>
                <td className="px-4 py-3 tabular-nums">{shekels(row.total_spent_agorot)}</td>
                <td className="px-4 py-3 text-xs text-ink/55">{dateOnly(row.created_at)}</td>
                <td className="px-4 py-3">
                  <span
                    className={`chip !px-2 !py-0.5 !text-[11px] ${
                      row.is_active ? 'bg-teal/25 text-teal-deep' : 'bg-red-100 text-red-700'
                    }`}
                  >
                    {row.is_active ? 'פעיל' : 'חסום'}
                  </span>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
        {data?.items.length === 0 && (
          <p className="p-6 text-center text-ink/55">לא נמצאו חברים</p>
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

      {selected !== null && (
        <MemberDrawer userId={selected} onClose={() => setSelected(null)} />
      )}
    </div>
  )
}
