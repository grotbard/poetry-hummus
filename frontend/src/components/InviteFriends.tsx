import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { api } from '../lib/api'
import { dateOnly } from '../lib/format'
import type { ReferralSummary } from '../lib/types'
import { Chickpea, CoinAmount } from './Chickpea'

/** Invite panel: share a link, see who joined, track coins earned. */
export function InviteFriends() {
  const [copied, setCopied] = useState(false)

  const { data, isLoading } = useQuery({
    queryKey: ['referrals'],
    queryFn: () => api.get<ReferralSummary>('/api/referrals'),
  })

  if (isLoading || !data) return null

  async function share() {
    const text = `בואו למועדון של חומוס המשורר — נרשמים דרך הקישור ומקבלים מטבעות מתנה: ${data!.link}`
    // The share sheet is a phone affordance; on desktop it is usually absent
    // or unhelpful, so only reach for it on a touch device.
    const isTouch = matchMedia('(pointer: coarse)').matches
    if (isTouch && navigator.share) {
      try {
        await navigator.share({ title: 'חומוס המשורר', text, url: data!.link })
        return
      } catch {
        /* dismissed — fall through to copying */
      }
    }
    try {
      await navigator.clipboard.writeText(data!.link)
      setCopied(true)
      setTimeout(() => setCopied(false), 2500)
    } catch {
      /* clipboard blocked; the link is on screen to copy by hand */
    }
  }

  const full = data.slots_left === 0

  return (
    <section className="card p-5">
      <div className="flex flex-wrap items-baseline justify-between gap-2">
        <h2 className="text-lg text-wine">הזמנת חברים</h2>
        <p className="text-xs text-ink/50">
          {data.completed_count} מתוך {data.max_friends} חברים
        </p>
      </div>

      <p className="mt-1 flex flex-wrap items-center gap-1 text-sm text-ink/65">
        <Chickpea className="h-4 w-4 shrink-0" />
        <span>
          שתפו את הקישור. כל חבר שנרשם מקבל {data.friend_bonus_coins} מטבעות
          מתנה, ואתם מקבלים {data.coins_per_friend} מטבעות אחרי ההזמנה הראשונה
          שלו.
        </span>
      </p>

      {full ? (
        <p className="mt-4 rounded-2xl bg-chickpea/20 px-4 py-3 text-center text-sm text-wine-dark">
          הגעתם למקסימום {data.max_friends} חברים — תודה!
        </p>
      ) : (
        <>
          <div className="mt-4 flex items-center gap-2">
            <code
              dir="ltr"
              className="flex-1 overflow-x-auto whitespace-nowrap rounded-2xl
                         bg-hummus/40 px-3 py-2.5 text-xs text-ink/70"
            >
              {data.link}
            </code>
            <button onClick={share} className="btn-primary shrink-0 !px-4 !py-2 text-sm">
              {copied ? 'הועתק ✓' : 'שיתוף'}
            </button>
          </div>
          <p className="mt-2 text-xs text-ink/45">
            נותרו {data.slots_left} מקומות
          </p>
        </>
      )}

      {data.friends.length > 0 && (
        <ul className="mt-4 space-y-1.5 border-t border-ink/10 pt-3">
          {data.friends.map((friend, i) => (
            <li key={i} className="flex items-center justify-between gap-2 text-sm">
              <span className="flex items-center gap-2">
                <Chickpea className="h-4 w-4 shrink-0" />
                {friend.name}
              </span>
              {friend.completed ? (
                <span className="flex items-center gap-1.5 text-teal-deep">
                  <CoinAmount value={friend.coins_earned} size="sm" signed />
                </span>
              ) : (
                <span className="text-xs text-ink/45">
                  ממתין להזמנה ראשונה · {dateOnly(friend.joined_at)}
                </span>
              )}
            </li>
          ))}
        </ul>
      )}
    </section>
  )
}
