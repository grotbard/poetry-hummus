import { useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { api } from '../../lib/api'
import { dateTime } from '../../lib/format'
import type { AdminUserRow, Paginated } from '../../lib/types'

/**
 * Members who cannot order because their phone is unconfirmed — the fallback
 * when SMS does not reach someone. Approving here is equivalent to passing a
 * real code, so each approval is written to the activity log.
 */
export function AdminApprovals() {
  const queryClient = useQueryClient()
  const [phones, setPhones] = useState<Record<number, string>>({})
  const [error, setError] = useState('')

  const { data, isLoading } = useQuery({
    queryKey: ['admin', 'approvals'],
    queryFn: () =>
      api.get<Paginated<AdminUserRow>>(
        '/api/admin/users?pending_phone=true&page_size=100',
      ),
    refetchInterval: 30_000,
  })

  const approve = useMutation({
    mutationFn: ({ id, phone }: { id: number; phone: string }) =>
      api.post(`/api/admin/users/${id}/verify-phone`, { phone }),
    onSuccess: async () => {
      setError('')
      await queryClient.invalidateQueries({ queryKey: ['admin'] })
    },
    onError: (e) => setError((e as Error).message),
  })

  if (isLoading) return <p className="text-ink/50">טוען…</p>

  const waiting = data?.items ?? []

  if (waiting.length === 0) {
    return (
      <div className="card p-8 text-center">
        <p className="text-ink/60">אין חברים שממתינים לאישור</p>
        <p className="mt-1 text-sm text-ink/45">
          כל החברים אימתו את מספר הטלפון שלהם
        </p>
      </div>
    )
  }

  return (
    <div className="space-y-4">
      <div className="rounded-2xl bg-chickpea/15 px-4 py-3 text-sm text-wine-dark">
        חברים שלא הצליחו לאמת את הטלפון בעצמם. אישור כאן שקול לאימות אמיתי —
        ודאו את המספר מול הלקוח לפני האישור. כל אישור נרשם ביומן הפעילות.
      </div>

      {error && (
        <p className="rounded-2xl bg-red-50 px-4 py-2 text-sm text-red-700">{error}</p>
      )}

      <div className="card divide-y divide-ink/[0.07]">
        {waiting.map((member) => {
          // Prefer a number already on file; the admin can correct it.
          const value = phones[member.id] ?? member.phone ?? ''
          const busy = approve.isPending && approve.variables?.id === member.id
          return (
            <div
              key={member.id}
              className="flex flex-wrap items-center gap-3 px-4 py-3"
            >
              <div className="min-w-0 flex-1">
                <p className="truncate font-medium">
                  {member.full_name || '(ללא שם)'}
                </p>
                <p className="truncate text-xs text-ink/50">{member.email}</p>
                <p className="mt-0.5 text-xs text-ink/40">
                  נרשם {dateTime(member.created_at)}
                </p>
              </div>

              <input
                className="input max-w-[11rem] text-sm"
                type="tel"
                dir="ltr"
                placeholder="05X-XXXXXXX"
                value={value}
                onChange={(e) =>
                  setPhones((prev) => ({ ...prev, [member.id]: e.target.value }))
                }
              />

              <button
                onClick={() => approve.mutate({ id: member.id, phone: value })}
                disabled={value.trim().length < 9 || busy}
                className="btn-primary shrink-0 !px-4 !py-2 text-sm"
              >
                {busy ? 'מאשר…' : 'אישור'}
              </button>
            </div>
          )
        })}
      </div>
    </div>
  )
}
