import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { api } from '../../lib/api'
import { CATEGORY_LABELS, shekels } from '../../lib/format'
import type { MenuItem } from '../../lib/types'

export function AdminMenu() {
  const queryClient = useQueryClient()

  const { data: items = [], isLoading } = useQuery({
    queryKey: ['admin', 'menu'],
    queryFn: () => api.get<MenuItem[]>('/api/admin/menu'),
  })

  const patch = useMutation({
    mutationFn: ({ id, body }: { id: number; body: Partial<MenuItem> }) =>
      api.patch<MenuItem>(`/api/admin/menu/${id}`, body),
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: ['admin', 'menu'] })
      await queryClient.invalidateQueries({ queryKey: ['menu'] })
    },
  })

  if (isLoading) return <p className="text-ink/50">טוען תפריט…</p>

  const grouped = new Map<string, MenuItem[]>()
  for (const item of items) {
    const list = grouped.get(item.category) ?? []
    list.push(item)
    grouped.set(item.category, list)
  }

  return (
    <div className="space-y-6">
      <p className="text-sm text-ink/55">
        שינוי מחיר או זמינות משתקף מיד באפליקציה. הזמנות עבר שומרות את המחיר שהיה בעת ההזמנה.
      </p>

      {patch.isError && (
        <p className="text-sm text-red-600">{(patch.error as Error).message}</p>
      )}

      {[...grouped.entries()].map(([category, group]) => (
        <section key={category}>
          <h2 className="mb-2 text-lg text-wine">{CATEGORY_LABELS[category] ?? category}</h2>
          <div className="card divide-y divide-ink/[0.07]">
            {group.map((item) => (
              <div key={item.id} className="flex flex-wrap items-center gap-3 px-4 py-3">
                <span className="text-2xl leading-none" aria-hidden>
                  {item.emoji || '🫛'}
                </span>
                <div className="min-w-0 flex-1">
                  <p className="truncate font-medium">{item.name_he}</p>
                  <p className="truncate text-xs text-ink/50">{item.name_en}</p>
                </div>

                <label className="flex items-center gap-1.5 text-sm">
                  <span className="text-xs text-ink/50">₪</span>
                  <input
                    type="number"
                    step="0.5"
                    defaultValue={(item.price_agorot / 100).toFixed(2)}
                    onBlur={(e) => {
                      const next = Math.round(Number(e.target.value) * 100)
                      if (next >= 0 && next !== item.price_agorot) {
                        patch.mutate({ id: item.id, body: { price_agorot: next } })
                      }
                    }}
                    className="w-20 rounded-xl border border-ink/15 px-2 py-1 text-sm tabular-nums outline-none focus:border-teal-deep"
                  />
                </label>

                <span className="w-16 shrink-0 text-right text-xs text-ink/45 tabular-nums">
                  {shekels(item.price_agorot)}
                </span>

                <button
                  onClick={() =>
                    patch.mutate({ id: item.id, body: { is_available: !item.is_available } })
                  }
                  className={`chip shrink-0 !px-3 !py-1 ${
                    item.is_available
                      ? 'bg-teal/25 text-teal-deep'
                      : 'bg-ink/10 text-ink/55'
                  }`}
                >
                  {item.is_available ? 'זמין' : 'לא זמין'}
                </button>
              </div>
            ))}
          </div>
        </section>
      ))}
    </div>
  )
}
