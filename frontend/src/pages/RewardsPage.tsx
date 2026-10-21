import { useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { api } from '../lib/api'
import { useAuth } from '../lib/auth'
import type { Reward } from '../lib/types'
import { Chickpea, CoinAmount } from '../components/Chickpea'

interface RedeemResult {
  reward: string
  coins_spent: number
  balance: number
  voucher_code: string
}

export function RewardsPage() {
  const { user, refresh } = useAuth()
  const queryClient = useQueryClient()
  const [voucher, setVoucher] = useState<RedeemResult | null>(null)

  const { data: rewards = [], isLoading } = useQuery({
    queryKey: ['rewards'],
    queryFn: () => api.get<Reward[]>('/api/rewards'),
  })

  const redeem = useMutation({
    mutationFn: (id: number) => api.post<RedeemResult>(`/api/rewards/${id}/redeem`),
    onSuccess: async (result) => {
      setVoucher(result)
      await refresh()
      await queryClient.invalidateQueries({ queryKey: ['coins'] })
    },
  })

  const balance = user?.coin_balance ?? 0

  if (voucher) {
    return (
      <div className="card mx-auto max-w-md p-8 text-center">
        <Chickpea className="coin-pop mx-auto h-16 w-16" />
        <h2 className="mt-4 text-2xl text-wine">{voucher.reward}</h2>
        <p className="mt-2 text-sm text-ink/60">הציגו את הקוד בקופה</p>
        <p className="my-5 rounded-2xl bg-hummus/50 py-4 font-mono text-2xl font-bold tracking-wider text-wine-dark">
          {voucher.voucher_code}
        </p>
        <p className="text-sm text-ink/60">
          יתרה חדשה: <CoinAmount value={voucher.balance} size="sm" />
        </p>
        <button onClick={() => setVoucher(null)} className="btn-primary mt-6">
          חזרה להטבות
        </button>
      </div>
    )
  }

  return (
    <div className="space-y-5">
      <div className="card flex items-center justify-between gap-3 px-5 py-4">
        <p className="text-sm text-ink/60">היתרה שלך</p>
        <CoinAmount value={balance} size="lg" className="text-wine" />
      </div>

      {isLoading && <p className="text-ink/50">טוען הטבות…</p>}
      {redeem.isError && (
        <p className="text-sm text-red-600">{(redeem.error as Error).message}</p>
      )}

      <div className="grid gap-3 sm:grid-cols-2">
        {rewards.map((reward) => {
          const affordable = balance >= reward.cost_coins
          const progress = Math.min(100, (balance / reward.cost_coins) * 100)
          return (
            <article key={reward.id} className="card flex flex-col p-5">
              <div className="flex items-start gap-3">
                <span className="text-3xl leading-none" aria-hidden>
                  {reward.emoji || '🎁'}
                </span>
                <div className="min-w-0 flex-1">
                  <h3 className="font-display text-base">{reward.name_he}</h3>
                  <p className="mt-0.5 text-sm text-ink/55">{reward.description_he}</p>
                </div>
              </div>

              <div className="mt-4 flex items-center justify-between gap-2">
                <CoinAmount value={reward.cost_coins} size="sm" className="text-wine" />
                <button
                  onClick={() => redeem.mutate(reward.id)}
                  disabled={!affordable || redeem.isPending}
                  className={affordable ? 'btn-primary !px-4 !py-1.5 text-sm' : 'btn-ghost !px-4 !py-1.5 text-sm'}
                >
                  {affordable ? 'מימוש' : `חסרים ${reward.cost_coins - balance}`}
                </button>
              </div>

              {!affordable && (
                <div className="mt-3 h-1.5 overflow-hidden rounded-full bg-ink/10">
                  <div
                    className="h-full rounded-full bg-chickpea transition-all"
                    style={{ width: `${progress}%` }}
                  />
                </div>
              )}
            </article>
          )
        })}
      </div>
    </div>
  )
}
