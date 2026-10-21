import { useQuery } from '@tanstack/react-query'
import { api } from '../../lib/api'
import { shekels } from '../../lib/format'
import type { AdminStats, CoinRules } from '../../lib/types'
import { Chickpea } from '../../components/Chickpea'

function Tile({
  label,
  value,
  hint,
  accent = false,
}: {
  label: string
  value: string
  hint?: string
  accent?: boolean
}) {
  return (
    <div className={`card p-5 ${accent ? 'bg-wine/95 text-hummus-light' : ''}`}>
      <p className={`text-xs ${accent ? 'opacity-75' : 'text-ink/50'}`}>{label}</p>
      <p className="mt-1.5 text-2xl font-black tabular-nums">{value}</p>
      {hint && <p className={`mt-1 text-xs ${accent ? 'opacity-70' : 'text-ink/45'}`}>{hint}</p>}
    </div>
  )
}

export function AdminOverview() {
  const { data, isLoading } = useQuery({
    queryKey: ['admin', 'stats'],
    queryFn: () => api.get<AdminStats>('/api/admin/stats'),
    refetchInterval: 30_000,
  })
  const { data: rules } = useQuery({
    queryKey: ['coin-rules'],
    queryFn: () => api.get<CoinRules>('/api/coins/rules'),
  })

  if (isLoading || !data) return <p className="text-ink/50">טוען נתונים…</p>

  return (
    <div className="space-y-6">
      <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
        <Tile label="חברי מועדון" value={data.total_members.toLocaleString('he-IL')} />
        <Tile
          label="הזמנות פעילות"
          value={data.active_orders.toLocaleString('he-IL')}
          hint="ממתינות / בהכנה / מוכנות"
          accent={data.active_orders > 0}
        />
        <Tile
          label="הזמנות היום"
          value={data.orders_today.toLocaleString('he-IL')}
          hint={`${data.total_orders.toLocaleString('he-IL')} בסך הכל`}
        />
        <Tile
          label="הכנסות היום"
          value={shekels(data.revenue_today_agorot)}
          hint={`${shekels(data.revenue_agorot)} בסך הכל`}
        />
      </div>

      <section className="card p-6">
        <h2 className="flex items-center gap-2 text-lg text-wine">
          <Chickpea className="h-5 w-5" />
          מטבעות משורר
        </h2>
        <div className="mt-4 grid gap-4 sm:grid-cols-3">
          <div>
            <p className="text-xs text-ink/50">יתרה פתוחה אצל החברים</p>
            <p className="mt-1 text-2xl font-black tabular-nums text-wine">
              {data.coins_outstanding.toLocaleString('he-IL')}
            </p>
            <p className="mt-1 text-xs text-ink/45">
              התחייבות: {shekels(data.coins_outstanding * (rules?.agorot_per_coin ?? 100))}
            </p>
          </div>
          <div>
            <p className="text-xs text-ink/50">הונפקו מאז ומתמיד</p>
            <p className="mt-1 text-2xl font-black tabular-nums text-teal-deep">
              {data.coins_issued.toLocaleString('he-IL')}
            </p>
          </div>
          <div>
            <p className="text-xs text-ink/50">מומשו</p>
            <p className="mt-1 text-2xl font-black tabular-nums text-chickpea">
              {data.coins_redeemed.toLocaleString('he-IL')}
            </p>
            <p className="mt-1 text-xs text-ink/45">
              {data.coins_issued > 0
                ? `${Math.round((data.coins_redeemed / data.coins_issued) * 100)}% שיעור מימוש`
                : '—'}
            </p>
          </div>
        </div>

        {data.coins_issued > 0 && (
          <div className="mt-5">
            <div className="flex h-2.5 overflow-hidden rounded-full bg-ink/10">
              <div
                className="bg-chickpea"
                style={{ width: `${(data.coins_redeemed / data.coins_issued) * 100}%` }}
              />
              <div className="flex-1 bg-teal/40" />
            </div>
            <div className="mt-2 flex justify-between text-[11px] text-ink/45">
              <span>מומשו</span>
              <span>פתוחות</span>
            </div>
          </div>
        )}
      </section>
    </div>
  )
}
