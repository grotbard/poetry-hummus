import { useState } from 'react'
import { useMutation, useQueryClient } from '@tanstack/react-query'
import { api } from '../../lib/api'
import { CATEGORY_LABELS } from '../../lib/format'
import type { MenuItem } from '../../lib/types'

const CATEGORIES = ['hummus', 'mains', 'sides', 'drinks', 'desserts', 'other']

export function MenuItemForm({ onClose }: { onClose: () => void }) {
  const queryClient = useQueryClient()
  const [nameHe, setNameHe] = useState('')
  const [nameEn, setNameEn] = useState('')
  const [description, setDescription] = useState('')
  const [category, setCategory] = useState('hummus')
  const [price, setPrice] = useState('')
  const [emoji, setEmoji] = useState('')
  const [isVegan, setIsVegan] = useState(false)

  const create = useMutation({
    mutationFn: () =>
      api.post<MenuItem>('/api/admin/menu', {
        name_he: nameHe.trim(),
        name_en: nameEn.trim(),
        description_he: description.trim(),
        category,
        price_agorot: Math.round(Number(price) * 100),
        emoji: emoji.trim(),
        is_vegan: isVegan,
        is_available: true,
      }),
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: ['admin', 'menu'] })
      await queryClient.invalidateQueries({ queryKey: ['menu'] })
      onClose()
    },
  })

  const priceValid = price !== '' && Number(price) >= 0
  const canSubmit = nameHe.trim().length > 0 && priceValid && !create.isPending

  return (
    <div className="fixed inset-0 z-40 grid place-items-center p-4" role="dialog" aria-modal="true">
      <button className="absolute inset-0 bg-ink/40 backdrop-blur-sm" onClick={onClose} aria-label="סגירה" />
      <div className="card relative w-full max-w-lg overflow-y-auto p-6" style={{ maxHeight: '90vh' }}>
        <h2 className="mb-4 font-display text-xl text-wine">מנה חדשה</h2>

        <div className="space-y-3">
          <div>
            <label className="mb-1 block text-xs text-ink/55">שם בעברית *</label>
            <input
              className="input"
              value={nameHe}
              onChange={(e) => setNameHe(e.target.value)}
              placeholder="חומוס פטריות"
              autoFocus
            />
          </div>

          <div className="grid grid-cols-2 gap-3">
            <div>
              <label className="mb-1 block text-xs text-ink/55">שם באנגלית</label>
              <input
                className="input"
                value={nameEn}
                onChange={(e) => setNameEn(e.target.value)}
                placeholder="Mushroom Hummus"
                dir="ltr"
              />
            </div>
            <div>
              <label className="mb-1 block text-xs text-ink/55">אימוג׳י</label>
              <input
                className="input"
                value={emoji}
                onChange={(e) => setEmoji(e.target.value)}
                placeholder="🍄"
                maxLength={8}
              />
            </div>
          </div>

          <div>
            <label className="mb-1 block text-xs text-ink/55">תיאור</label>
            <textarea
              className="input"
              rows={2}
              value={description}
              onChange={(e) => setDescription(e.target.value)}
              placeholder="חומוס עם פטריות מוקפצות בשום ויין"
            />
          </div>

          <div className="grid grid-cols-2 gap-3">
            <div>
              <label className="mb-1 block text-xs text-ink/55">קטגוריה</label>
              <select className="input" value={category} onChange={(e) => setCategory(e.target.value)}>
                {CATEGORIES.map((c) => (
                  <option key={c} value={c}>
                    {CATEGORY_LABELS[c] ?? c}
                  </option>
                ))}
              </select>
            </div>
            <div>
              <label className="mb-1 block text-xs text-ink/55">מחיר (₪) *</label>
              <input
                className="input"
                type="number"
                step="0.5"
                min="0"
                value={price}
                onChange={(e) => setPrice(e.target.value)}
                placeholder="42"
              />
            </div>
          </div>

          <label className="flex cursor-pointer items-center gap-2 text-sm">
            <input
              type="checkbox"
              checked={isVegan}
              onChange={(e) => setIsVegan(e.target.checked)}
              className="h-4 w-4 accent-teal-deep"
            />
            מנה טבעונית
          </label>

          {create.isError && (
            <p className="text-sm text-red-600">{(create.error as Error).message}</p>
          )}

          <div className="flex gap-2 pt-2">
            <button onClick={() => create.mutate()} disabled={!canSubmit} className="btn-primary flex-1">
              {create.isPending ? 'מוסיף…' : 'הוספת מנה'}
            </button>
            <button onClick={onClose} className="btn-ghost">
              ביטול
            </button>
          </div>
          <p className="text-center text-[11px] text-ink/45">
            תמונה אפשר להעלות אחרי היצירה, מתוך רשימת התפריט
          </p>
        </div>
      </div>
    </div>
  )
}
