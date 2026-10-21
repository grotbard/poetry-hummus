import { useState } from 'react'
import { useMutation, useQueryClient } from '@tanstack/react-query'
import { api } from '../lib/api'
import { useAuth } from '../lib/auth'
import type { FeedbackResult, Order } from '../lib/types'
import { Chickpea, CoinAmount } from './Chickpea'

/** Two taps: rate the food, rate the service, collect the coins. */
export function FeedbackCard({
  order,
  onRated,
}: {
  order: Order
  onRated?: () => void
}) {
  const { refresh } = useAuth()
  const queryClient = useQueryClient()
  const [food, setFood] = useState(0)
  const [service, setService] = useState(0)
  const [result, setResult] = useState<FeedbackResult | null>(null)

  const send = useMutation({
    mutationFn: () =>
      api.post<FeedbackResult>(`/api/orders/${order.id}/feedback`, { food, service }),
    onSuccess: async (data) => {
      setResult(data)
      onRated?.()
      await refresh()
      await queryClient.invalidateQueries({ queryKey: ['orders'] })
      await queryClient.invalidateQueries({ queryKey: ['coins'] })
    },
  })

  if (result) {
    return (
      <div className="mt-3 rounded-2xl bg-teal/15 px-4 py-3 text-center">
        {result.coins_granted > 0 ? (
          <>
            <Chickpea className="coin-pop mx-auto h-8 w-8" />
            <p className="mt-1.5 text-sm font-medium text-teal-deep">
              תודה! נוספו לך <CoinAmount value={result.coins_granted} size="sm" /> מטבעות
            </p>
          </>
        ) : (
          <p className="text-sm text-ink/70">תודה על המשוב!</p>
        )}
      </div>
    )
  }

  return (
    <div className="mt-3 rounded-2xl bg-chickpea/15 p-4">
      <p className="text-sm font-medium text-wine">
        {order.coins_pending > 0 ? (
          <>
            דרגו את ההזמנה וקבלו{' '}
            <CoinAmount value={order.coins_pending} size="sm" className="text-wine" />{' '}
            מטבעות
          </>
        ) : (
          'איך היה?'
        )}
      </p>

      <Stars label="החומוס" value={food} onChange={setFood} />
      <Stars label="השירות" value={service} onChange={setService} />

      {send.isError && (
        <p className="mt-2 text-sm text-red-600">{(send.error as Error).message}</p>
      )}

      <button
        onClick={() => send.mutate()}
        disabled={!food || !service || send.isPending}
        className="btn-primary mt-3 w-full !py-2 text-sm"
      >
        {send.isPending ? 'שולח…' : 'שליחת דירוג'}
      </button>
    </div>
  )
}

function Stars({
  label,
  value,
  onChange,
}: {
  label: string
  value: number
  onChange: (n: number) => void
}) {
  return (
    <div className="mt-3 flex items-center justify-between gap-3">
      <span className="text-sm text-ink/70">{label}</span>
      <div className="flex gap-1" role="radiogroup" aria-label={label}>
        {[1, 2, 3, 4, 5].map((n) => (
          <button
            key={n}
            onClick={() => onChange(n)}
            role="radio"
            aria-checked={value === n}
            aria-label={`${n} מתוך 5`}
            className={`grid h-9 w-9 place-items-center rounded-full text-lg transition ${
              n <= value
                ? 'bg-wine text-hummus-light'
                : 'bg-white/70 text-ink/30 hover:bg-white'
            }`}
          >
            ★
          </button>
        ))}
      </div>
    </div>
  )
}
