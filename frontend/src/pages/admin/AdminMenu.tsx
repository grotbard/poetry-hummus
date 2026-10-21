import { useRef, useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { api, uploadFile } from '../../lib/api'
import { shekels } from '../../lib/format'
import type { MenuCategory, MenuItem } from '../../lib/types'
import { MenuItemForm } from './MenuItemForm'

export function AdminMenu() {
  const queryClient = useQueryClient()
  const [showForm, setShowForm] = useState(false)
  const [confirmDelete, setConfirmDelete] = useState<MenuItem | null>(null)
  const [busyItem, setBusyItem] = useState<number | null>(null)
  const [reordering, setReordering] = useState(false)
  const [error, setError] = useState('')

  const { data: items = [], isLoading } = useQuery({
    queryKey: ['admin', 'menu'],
    queryFn: () => api.get<MenuItem[]>('/api/admin/menu'),
  })
  const { data: categories = [] } = useQuery({
    queryKey: ['admin', 'categories'],
    queryFn: () => api.get<MenuCategory[]>('/api/admin/categories'),
  })

  const refresh = async () => {
    await queryClient.invalidateQueries({ queryKey: ['admin', 'menu'] })
    await queryClient.invalidateQueries({ queryKey: ['admin', 'categories'] })
    await queryClient.invalidateQueries({ queryKey: ['menu'] })
    await queryClient.invalidateQueries({ queryKey: ['categories'] })
  }

  /** Move one entry of `ids` by `delta` and persist the new order. */
  async function move(endpoint: string, ids: number[], index: number, delta: number) {
    const target = index + delta
    if (target < 0 || target >= ids.length) return
    const next = [...ids]
    ;[next[index], next[target]] = [next[target], next[index]]
    setError('')
    setReordering(true)
    try {
      await api.post(endpoint, { ids: next })
      await refresh()
    } catch (e) {
      setError((e as Error).message)
    } finally {
      setReordering(false)
    }
  }

  const patch = useMutation({
    mutationFn: ({ id, body }: { id: number; body: Partial<MenuItem> }) =>
      api.patch<MenuItem>(`/api/admin/menu/${id}`, body),
    onSuccess: refresh,
    onError: (e) => setError((e as Error).message),
  })

  const remove = useMutation({
    mutationFn: (id: number) => api.del<void>(`/api/admin/menu/${id}`),
    onSuccess: async () => {
      setConfirmDelete(null)
      await refresh()
    },
    onError: (e) => setError((e as Error).message),
  })

  async function handleUpload(item: MenuItem, file: File) {
    setError('')
    setBusyItem(item.id)
    try {
      await uploadFile<MenuItem>(`/api/admin/menu/${item.id}/image`, file)
      await refresh()
    } catch (e) {
      setError((e as Error).message)
    } finally {
      setBusyItem(null)
    }
  }

  async function handleRemoveImage(item: MenuItem) {
    setError('')
    setBusyItem(item.id)
    try {
      await api.del<MenuItem>(`/api/admin/menu/${item.id}/image`)
      await refresh()
    } catch (e) {
      setError((e as Error).message)
    } finally {
      setBusyItem(null)
    }
  }

  if (isLoading) return <p className="text-ink/50">טוען תפריט…</p>

  // Items arrive in category order; group them while preserving it.
  const grouped = new Map<string, MenuItem[]>()
  for (const item of items) {
    const list = grouped.get(item.category) ?? []
    list.push(item)
    grouped.set(item.category, list)
  }

  // Show every category that has items, plus empty ones the admin can reorder.
  const orderedKeys = [
    ...categories.map((c) => c.key).filter((k) => grouped.has(k)),
    ...[...grouped.keys()].filter((k) => !categories.some((c) => c.key === k)),
  ]
  const categoryIds = categories.filter((c) => grouped.has(c.key)).map((c) => c.id)
  const labelOf = (key: string) =>
    categories.find((c) => c.key === key)?.label_he ?? key

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <p className="text-sm text-ink/55">
          שינוי מחיר, תמונה או זמינות משתקף מיד באפליקציה. הזמנות עבר שומרות את המחיר שהיה בעת ההזמנה.
        </p>
        <button onClick={() => setShowForm(true)} className="btn-primary !px-4 !py-2 text-sm">
          + מנה חדשה
        </button>
      </div>

      {error && (
        <p className="rounded-2xl bg-red-50 px-4 py-2 text-sm text-red-700">{error}</p>
      )}

      {orderedKeys.map((category) => {
        const group = grouped.get(category) ?? []
        const itemIds = group.map((i) => i.id)
        const catIndex = categoryIds.indexOf(
          categories.find((c) => c.key === category)?.id ?? -1,
        )
        return (
        <section key={category}>
          <div className="mb-2 flex items-center gap-2">
            <h2 className="text-lg text-wine">{labelOf(category)}</h2>
            {catIndex >= 0 && (
              <div className="flex gap-0.5">
                <MoveButton
                  dir="up"
                  disabled={reordering || catIndex === 0}
                  title="העברת הקטגוריה למעלה"
                  onClick={() => move('/api/admin/categories/reorder', categoryIds, catIndex, -1)}
                />
                <MoveButton
                  dir="down"
                  disabled={reordering || catIndex === categoryIds.length - 1}
                  title="העברת הקטגוריה למטה"
                  onClick={() => move('/api/admin/categories/reorder', categoryIds, catIndex, 1)}
                />
              </div>
            )}
          </div>
          <div className="card divide-y divide-ink/[0.07]">
            {group.map((item, index) => (
              <MenuRow
                key={item.id}
                item={item}
                busy={busyItem === item.id || patch.isPending || reordering}
                canMoveUp={index > 0}
                canMoveDown={index < group.length - 1}
                onMove={(delta) => move('/api/admin/menu/reorder', itemIds, index, delta)}
                onUpload={(file) => handleUpload(item, file)}
                onRemoveImage={() => handleRemoveImage(item)}
                onPrice={(price_agorot) => patch.mutate({ id: item.id, body: { price_agorot } })}
                onToggle={() =>
                  patch.mutate({ id: item.id, body: { is_available: !item.is_available } })
                }
                onDelete={() => setConfirmDelete(item)}
              />
            ))}
          </div>
        </section>
        )
      })}

      {showForm && <MenuItemForm onClose={() => setShowForm(false)} />}

      {confirmDelete && (
        <div className="fixed inset-0 z-40 grid place-items-center p-4" role="dialog" aria-modal="true">
          <button
            className="absolute inset-0 bg-ink/40 backdrop-blur-sm"
            onClick={() => setConfirmDelete(null)}
            aria-label="סגירה"
          />
          <div className="card relative w-full max-w-sm p-6 text-center">
            <p className="text-lg">
              למחוק את <strong>{confirmDelete.name_he}</strong>?
            </p>
            <p className="mt-2 text-sm text-ink/55">
              אם המנה כבר הוזמנה בעבר היא תוסתר מהתפריט במקום להימחק, כדי לא לפגוע בהיסטוריית ההזמנות.
            </p>
            <div className="mt-5 flex gap-2">
              <button
                onClick={() => remove.mutate(confirmDelete.id)}
                disabled={remove.isPending}
                className="btn flex-1 bg-red-600 text-white hover:bg-red-700"
              >
                {remove.isPending ? 'מוחק…' : 'מחיקה'}
              </button>
              <button onClick={() => setConfirmDelete(null)} className="btn-ghost flex-1">
                ביטול
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}

function MoveButton({
  dir,
  disabled,
  title,
  onClick,
}: {
  dir: 'up' | 'down'
  disabled: boolean
  title: string
  onClick: () => void
}) {
  return (
    <button
      onClick={onClick}
      disabled={disabled}
      title={title}
      aria-label={title}
      className="grid h-6 w-6 place-items-center rounded-lg text-ink/45 transition
                 hover:bg-ink/10 hover:text-wine disabled:opacity-25
                 disabled:hover:bg-transparent"
    >
      {dir === 'up' ? '▲' : '▼'}
    </button>
  )
}

function MenuRow({
  item,
  busy,
  canMoveUp,
  canMoveDown,
  onMove,
  onUpload,
  onRemoveImage,
  onPrice,
  onToggle,
  onDelete,
}: {
  item: MenuItem
  busy: boolean
  canMoveUp: boolean
  canMoveDown: boolean
  onMove: (delta: number) => void
  onUpload: (file: File) => void
  onRemoveImage: () => void
  onPrice: (agorot: number) => void
  onToggle: () => void
  onDelete: () => void
}) {
  const fileInput = useRef<HTMLInputElement>(null)

  return (
    <div className="flex flex-wrap items-center gap-3 px-4 py-3">
      <div className="flex shrink-0 flex-col">
        <MoveButton
          dir="up"
          disabled={busy || !canMoveUp}
          title="העברה למעלה"
          onClick={() => onMove(-1)}
        />
        <MoveButton
          dir="down"
          disabled={busy || !canMoveDown}
          title="העברה למטה"
          onClick={() => onMove(1)}
        />
      </div>

      {/* Thumbnail doubles as the upload trigger. */}
      <button
        onClick={() => fileInput.current?.click()}
        disabled={busy}
        title="העלאת תמונה"
        className="group relative grid h-14 w-14 shrink-0 place-items-center overflow-hidden rounded-2xl bg-hummus/40 transition hover:ring-2 hover:ring-teal-deep"
      >
        {item.image_url ? (
          <img src={item.image_url} alt="" className="h-full w-full object-cover" />
        ) : (
          <span className="text-2xl leading-none" aria-hidden>
            {item.emoji || '🫛'}
          </span>
        )}
        <span className="absolute inset-0 hidden place-items-center bg-ink/55 text-[10px] font-medium text-white group-hover:grid">
          {busy ? '…' : 'תמונה'}
        </span>
      </button>
      <input
        ref={fileInput}
        type="file"
        accept="image/jpeg,image/png,image/gif,image/webp"
        className="hidden"
        onChange={(e) => {
          const file = e.target.files?.[0]
          if (file) onUpload(file)
          e.target.value = ''
        }}
      />

      <div className="min-w-0 flex-1">
        <p className="truncate font-medium">{item.name_he}</p>
        <p className="truncate text-xs text-ink/50">{item.name_en}</p>
        {item.image_url && (
          <button
            onClick={onRemoveImage}
            disabled={busy}
            className="mt-0.5 text-[11px] text-ink/45 hover:text-red-600"
          >
            הסרת תמונה
          </button>
        )}
      </div>

      <label className="flex items-center gap-1.5 text-sm">
        <span className="text-xs text-ink/50">₪</span>
        <input
          type="number"
          step="0.5"
          min="0"
          defaultValue={(item.price_agorot / 100).toFixed(2)}
          onBlur={(e) => {
            const next = Math.round(Number(e.target.value) * 100)
            if (next >= 0 && next !== item.price_agorot) onPrice(next)
          }}
          className="w-20 rounded-xl border border-ink/15 px-2 py-1 text-sm tabular-nums outline-none focus:border-teal-deep"
        />
      </label>

      <span className="w-16 shrink-0 text-right text-xs tabular-nums text-ink/45">
        {shekels(item.price_agorot)}
      </span>

      <button
        onClick={onToggle}
        disabled={busy}
        className={`chip shrink-0 !px-3 !py-1 ${
          item.is_available ? 'bg-teal/25 text-teal-deep' : 'bg-ink/10 text-ink/55'
        }`}
      >
        {item.is_available ? 'זמין' : 'לא זמין'}
      </button>

      <button
        onClick={onDelete}
        disabled={busy}
        title="מחיקת מנה"
        className="shrink-0 rounded-full px-2 py-1 text-ink/35 transition hover:bg-red-50 hover:text-red-600"
      >
        ✕
      </button>
    </div>
  )
}
