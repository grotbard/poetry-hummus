export function shekels(agorot: number): string {
  return new Intl.NumberFormat('he-IL', {
    style: 'currency',
    currency: 'ILS',
    minimumFractionDigits: agorot % 100 === 0 ? 0 : 2,
  }).format(agorot / 100)
}

export function dateTime(iso: string): string {
  return new Intl.DateTimeFormat('he-IL', {
    dateStyle: 'short',
    timeStyle: 'short',
  }).format(new Date(iso))
}

export function dateOnly(iso: string): string {
  return new Intl.DateTimeFormat('he-IL', { dateStyle: 'medium' }).format(new Date(iso))
}

export const CATEGORY_LABELS: Record<string, string> = {
  hummus: 'חומוסים',
  mains: 'עיקריות',
  sides: 'תוספות וסלטים',
  drinks: 'שתייה',
  desserts: 'קינוחים',
  other: 'שונות',
}

export const STATUS_LABELS: Record<string, string> = {
  pending: 'ממתינה',
  preparing: 'בהכנה',
  ready: 'מוכנה לאיסוף',
  collected: 'נאספה',
  cancelled: 'בוטלה',
}

export const STATUS_STYLES: Record<string, string> = {
  pending: 'bg-chickpea/25 text-wine-dark',
  preparing: 'bg-teal/30 text-teal-deep',
  ready: 'bg-teal-deep text-white',
  collected: 'bg-ink/10 text-ink/70',
  cancelled: 'bg-red-100 text-red-700',
}

export const COIN_KIND_LABELS: Record<string, string> = {
  earn: 'צבירה מהזמנה',
  redeem: 'מימוש',
  signup_bonus: 'בונוס הרשמה',
  admin_adjust: 'עדכון מנהל',
  refund: 'החזר על ביטול',
  expired: 'פקיעת תוקף',
  referral: 'הזמנת חברים',
}

export const ACTION_LABELS: Record<string, string> = {
  'user.registered': 'נרשם למועדון',
  'user.login': 'התחברות',
  'admin.login': 'התחברות מנהל',
  'order.created': 'הזמנה נוצרה',
  'order.paid': 'הזמנה שולמה',
  'order.status_changed': 'שינוי סטטוס הזמנה',
  'reward.redeemed': 'מימוש הטבה',
  'admin.coins_adjusted': 'מנהל עדכן מטבעות',
  'admin.user_toggled': 'מנהל שינה סטטוס חבר',
  'order.feedback_submitted': 'דירוג הזמנה',
  'coins.expired': 'מטבעות פקעו',
  'referral.joined': 'הצטרף דרך הזמנת חבר',
  'referral.completed': 'הזמנת חבר הושלמה',
  'referral.capped': 'הזמנת חבר מעל התקרה',
}
