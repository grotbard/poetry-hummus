import { useMemo, useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { api } from '../lib/api'
import { useAuth } from '../lib/auth'
import { CATEGORY_LABELS, shekels } from '../lib/format'
import type { CoinRules, MenuCategory, MenuItem, Order } from '../lib/types'
import { Chickpea, CoinAmount } from '../components/Chickpea'

/** Cart lines are keyed by dish *and* egg count, so "+1 egg" is its own line. */
interface CartLine {
  menuItemId: number
  eggs: number
  quantity: number
}
type Cart = Record<string, CartLine>

const lineKey = (menuItemId: number, eggs: number) => `${menuItemId}:${eggs}`

export function MenuPage() {
  const { user, refresh } = useAuth()
  const queryClient = useQueryClient()
  const [cart, setCart] = useState<Cart>({})
  const [note, setNote] = useState('')
  const [redeem, setRedeem] = useState(0)
  const [placed, setPlaced] = useState<Order | null>(null)

  const { data: menu = [], isLoading } = useQuery({
    queryKey: ['menu'],
    queryFn: () => api.get<MenuItem[]>('/api/menu'),
  })
  const { data: rules } = useQuery({
    queryKey: ['coin-rules'],
    queryFn: () => api.get<CoinRules>('/api/coins/rules'),
  })
  const { data: categories = [] } = useQuery({
    queryKey: ['categories'],
    queryFn: () => api.get<MenuCategory[]>('/api/categories'),
  })

  const byId = useMemo(() => new Map(menu.map((m) => [m.id, m])), [menu])
  // The API already returns items in category order, so insertion order here
  // reproduces it; `categories` supplies the Hebrew label.
  const grouped = useMemo(() => {
    const out = new Map<string, MenuItem[]>()
    for (const item of menu) {
      const list = out.get(item.category) ?? []
      list.push(item)
      out.set(item.category, list)
    }
    return out
  }, [menu])

  const labelFor = useMemo(() => {
    const byKey = new Map(categories.map((c) => [c.key, c.label_he]))
    return (key: string) => byKey.get(key) ?? CATEGORY_LABELS[key] ?? key
  }, [categories])

  const eggPrice = rules?.egg_price_agorot ?? 300

  const subtotal = useMemo(
    () =>
      Object.values(cart).reduce((sum, line) => {
        const unit = byId.get(line.menuItemId)?.price_agorot ?? 0
        return sum + (unit + line.eggs * eggPrice) * line.quantity
      }, 0),
    [cart, byId, eggPrice],
  )

  // Mirror of the server's cap: half the bill, and never more than held.
  const maxRedeem = useMemo(() => {
    if (!user || !rules) return 0
    const capAgorot = Math.floor(subtotal * rules.max_redeem_fraction)
    return Math.max(0, Math.min(user.coin_balance, Math.floor(capAgorot / rules.agorot_per_coin)))
  }, [user, rules, subtotal])

  // The slider steps in 10s, so round the ceiling down to a reachable value;
  // otherwise the top of the track is unselectable.
  const sliderMax = Math.floor(maxRedeem / 10) * 10
  const effectiveRedeem = Math.min(redeem, sliderMax)
  const discount = effectiveRedeem * (rules?.agorot_per_coin ?? 10)
  const total = Math.max(0, subtotal - discount)
  // Mirrors coins_for_amount on the server: nothing below the minimum, then
  // a percentage of what is actually paid.
  const minOrder = rules?.earn_min_order_agorot ?? 4500
  const willEarn =
    total < minOrder ? 0 : Math.floor((total * (rules?.earn_percent ?? 5)) / 100 / 100)
  const itemCount = Object.values(cart).reduce((a, line) => a + line.quantity, 0)

  const placeOrder = useMutation({
    mutationFn: () =>
      api.post<Order>('/api/orders', {
        items: Object.values(cart).map((line) => ({
          menu_item_id: line.menuItemId,
          quantity: line.quantity,
          eggs: line.eggs,
        })),
        note,
        redeem_coins: effectiveRedeem,
      }),
    onSuccess: async (order) => {
      setPlaced(order)
      setCart({})
      setNote('')
      setRedeem(0)
      await refresh()
      await queryClient.invalidateQueries({ queryKey: ['orders'] })
      await queryClient.invalidateQueries({ queryKey: ['coins'] })
    },
  })

  function add(menuItemId: number, delta: number, eggs = 0) {
    setCart((prev) => {
      const next = { ...prev }
      const key = lineKey(menuItemId, eggs)
      const quantity = (next[key]?.quantity ?? 0) + delta
      if (quantity <= 0) delete next[key]
      else next[key] = { menuItemId, eggs, quantity: Math.min(quantity, 50) }
      return next
    })
  }

  /** Move a line to a different egg count, merging if that line exists. */
  function setEggs(menuItemId: number, fromEggs: number, toEggs: number) {
    if (toEggs < 0 || toEggs > 10) return
    setCart((prev) => {
      const from = prev[lineKey(menuItemId, fromEggs)]
      if (!from) return prev
      const next = { ...prev }
      delete next[lineKey(menuItemId, fromEggs)]
      const toKey = lineKey(menuItemId, toEggs)
      const existing = next[toKey]?.quantity ?? 0
      next[toKey] = {
        menuItemId,
        eggs: toEggs,
        quantity: Math.min(existing + from.quantity, 50),
      }
      return next
    })
  }

  if (placed) {
    return (
      <div className="card p-8 text-center max-w-lg mx-auto">
        <Chickpea className="w-16 h-16 mx-auto coin-pop" />
        <h2 className="mt-4 text-2xl text-wine">ההזמנה נשלחה!</h2>
        <p className="mt-1 text-ink/60">
          מספר הזמנה <strong className="font-mono">{placed.order_number}</strong>
        </p>
        <p className="mt-4 text-sm text-ink/70">
          לתשלום: <strong>{shekels(placed.total_agorot)}</strong>
        </p>
        <p className="mt-2 text-sm text-ink/70">
          אחרי האיסוף תוכלו לדרג את ההזמנה ולקבל את מטבעות המשורר
        </p>
        <button onClick={() => setPlaced(null)} className="btn-primary mt-6">
          להזמנה נוספת
        </button>
      </div>
    )
  }

  return (
    <div className="grid gap-6 lg:grid-cols-[1fr_20rem]">
      <div className="space-y-7">
        {isLoading && <p className="text-ink/50">טוען תפריט…</p>}
        {[...grouped.entries()].map(([category, items]) => (
          <section key={category}>
            <h2 className="mb-3 text-xl text-wine">
              {labelFor(category)}
            </h2>
            <div className="grid gap-3 sm:grid-cols-2">
              {items.map((item) => (
                <article
                  key={item.id}
                  className="card p-4 flex gap-3 items-start"
                >
                  {item.image_url ? (
                    <img
                      src={item.image_url}
                      alt=""
                      className="h-16 w-16 shrink-0 rounded-2xl object-cover"
                      loading="lazy"
                    />
                  ) : (
                    <span className="shrink-0 text-3xl leading-none" aria-hidden>
                      {item.emoji || '🫛'}
                    </span>
                  )}
                  <div className="min-w-0 flex-1">
                    <div className="flex items-baseline gap-2">
                      <h3 className="font-display text-base text-ink truncate">
                        {item.name_he}
                      </h3>
                      {item.is_vegan && (
                        <span className="chip bg-teal/25 text-teal-deep !text-[11px] !px-2 !py-0.5">
                          טבעוני
                        </span>
                      )}
                    </div>
                    {item.description_he && (
                      <p className="mt-1 text-sm text-ink/55 line-clamp-2">
                        {item.description_he}
                      </p>
                    )}
                    <div className="mt-3 flex items-center justify-between gap-2">
                      <span className="font-bold text-wine">
                        {shekels(item.price_agorot)}
                      </span>
                      {cart[lineKey(item.id, 0)] ? (
                        <div className="flex items-center gap-2">
                          <button
                            onClick={() => add(item.id, -1)}
                            className="w-8 h-8 rounded-full bg-ink/10 hover:bg-ink/20 text-lg leading-none"
                            aria-label="הפחתה"
                          >
                            −
                          </button>
                          <span className="w-6 text-center font-bold tabular-nums">
                            {cart[lineKey(item.id, 0)].quantity}
                          </span>
                          <button
                            onClick={() => add(item.id, 1)}
                            className="w-8 h-8 rounded-full bg-wine text-hummus-light hover:bg-wine-light text-lg leading-none"
                            aria-label="הוספה"
                          >
                            +
                          </button>
                        </div>
                      ) : (
                        <button
                          onClick={() => add(item.id, 1)}
                          className="btn-ghost !px-4 !py-1.5 text-sm"
                        >
                          הוספה
                        </button>
                      )}
                    </div>
                  </div>
                </article>
              ))}
            </div>
          </section>
        ))}
      </div>

      <aside className="lg:sticky lg:top-32 h-fit">
        <div className="card p-5">
          <h2 className="text-lg text-wine mb-3">העגלה</h2>
          {itemCount === 0 ? (
            <p className="text-sm text-ink/50">העגלה ריקה — בחרו מנה מהתפריט</p>
          ) : (
            <>
              <ul className="space-y-2 text-sm">
                {Object.entries(cart).map(([key, line]) => {
                  const item = byId.get(line.menuItemId)
                  if (!item) return null
                  const lineTotal =
                    (item.price_agorot + line.eggs * eggPrice) * line.quantity
                  return (
                    <li key={key}>
                      <div className="flex justify-between gap-2">
                        <span className="truncate">
                          {line.quantity} × {item.name_he}
                        </span>
                        <span className="shrink-0 tabular-nums">
                          {shekels(lineTotal)}
                        </span>
                      </div>
                      {item.allows_egg && (
                        <div className="mt-1 flex items-center gap-2 text-xs text-ink/55">
                          <span>🥚 ביצה</span>
                          <button
                            onClick={() => setEggs(item.id, line.eggs, line.eggs - 1)}
                            disabled={line.eggs === 0}
                            className="h-5 w-5 rounded-full bg-ink/10 leading-none hover:bg-ink/20 disabled:opacity-30"
                            aria-label="פחות ביצים"
                          >
                            −
                          </button>
                          <span className="w-4 text-center font-bold tabular-nums">
                            {line.eggs}
                          </span>
                          <button
                            onClick={() => setEggs(item.id, line.eggs, line.eggs + 1)}
                            className="h-5 w-5 rounded-full bg-wine text-hummus-light leading-none hover:bg-wine-light"
                            aria-label="עוד ביצה"
                          >
                            +
                          </button>
                          <span className="text-ink/40">
                            {shekels(eggPrice)} ליחידה
                          </span>
                        </div>
                      )}
                    </li>
                  )
                })}
              </ul>

              <textarea
                className="input mt-4 text-sm"
                rows={2}
                placeholder="הערות להזמנה (לא חריף, בלי בצל…)"
                value={note}
                onChange={(e) => setNote(e.target.value)}
              />

              {sliderMax > 0 && (
                <div className="mt-4 rounded-2xl bg-chickpea/15 p-3">
                  <label className="flex items-center justify-between text-sm font-medium">
                    <span>מימוש מטבעות</span>
                    <CoinAmount value={effectiveRedeem} size="sm" />
                  </label>
                  <input
                    type="range"
                    min={0}
                    max={sliderMax}
                    step={10}
                    value={effectiveRedeem}
                    onChange={(e) => setRedeem(Number(e.target.value))}
                    className="mt-2 w-full accent-wine"
                  />
                  <p className="mt-1 text-xs text-ink/55">
                    עד {sliderMax} מטבעות בהזמנה זו
                  </p>
                </div>
              )}

              <dl className="mt-4 space-y-1.5 border-t border-ink/10 pt-3 text-sm">
                <div className="flex justify-between">
                  <dt className="text-ink/60">סכום ביניים</dt>
                  <dd className="tabular-nums">{shekels(subtotal)}</dd>
                </div>
                {discount > 0 && (
                  <div className="flex justify-between text-teal-deep">
                    <dt>הנחת מטבעות</dt>
                    <dd className="tabular-nums">−{shekels(discount)}</dd>
                  </div>
                )}
                <div className="flex justify-between text-base font-bold text-wine">
                  <dt>לתשלום</dt>
                  <dd className="tabular-nums">{shekels(total)}</dd>
                </div>
                {willEarn > 0 ? (
                  <div className="flex justify-between pt-1 text-xs text-ink/55">
                    <dt>תצברו בהזמנה</dt>
                    <dd>
                      <CoinAmount value={willEarn} size="sm" />
                    </dd>
                  </div>
                ) : (
                  <p className="pt-1 text-xs text-ink/45">
                    הזמנות מעל {shekels(minOrder)} מזכות במטבעות
                  </p>
                )}
              </dl>

              {placeOrder.isError && (
                <p className="mt-3 text-sm text-red-600">
                  {(placeOrder.error as Error).message}
                </p>
              )}

              <button
                onClick={() => placeOrder.mutate()}
                disabled={placeOrder.isPending}
                className="btn-primary mt-4 w-full"
              >
                {placeOrder.isPending ? 'שולח…' : `הזמנה · ${shekels(total)}`}
              </button>
              <p className="mt-2 text-center text-[11px] text-ink/40">
                התשלום מתבצע באיסוף במסעדה
              </p>
            </>
          )}
        </div>
      </aside>
    </div>
  )
}
