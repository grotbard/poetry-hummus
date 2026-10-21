export type UserRole = 'member' | 'admin'
export type OrderStatus = 'pending' | 'preparing' | 'ready' | 'collected' | 'cancelled'
export type PaymentStatus = 'unpaid' | 'paid' | 'refunded'
export type CoinTxKind =
  | 'earn'
  | 'redeem'
  | 'signup_bonus'
  | 'admin_adjust'
  | 'refund'
  | 'expired'

export interface User {
  id: number
  email: string
  full_name: string
  picture_url: string | null
  phone: string | null
  role: UserRole
  is_active: boolean
  coin_balance: number
  lifetime_coins_earned: number
  created_at: string
  last_login_at: string | null
}

export interface MenuItem {
  id: number
  name_he: string
  name_en: string
  description_he: string
  category: string
  price_agorot: number
  emoji: string
  image_url: string | null
  is_available: boolean
  is_vegan: boolean
  allows_egg: boolean
  sort_order: number
}

export interface MenuCategory {
  id: number
  key: string
  label_he: string
  sort_order: number
}

export interface OrderItem {
  id: number
  menu_item_id: number | null
  name_snapshot: string
  unit_price_agorot: number
  quantity: number
  eggs: number
  egg_price_agorot: number
  line_total_agorot: number
}

export interface Order {
  id: number
  order_number: string
  status: OrderStatus
  payment_status: PaymentStatus
  subtotal_agorot: number
  discount_agorot: number
  total_agorot: number
  coins_spent: number
  coins_earned: number
  coins_pending: number
  feedback_food: number | null
  feedback_service: number | null
  feedback_at: string | null
  note: string
  created_at: string
  collected_at: string | null
  items: OrderItem[]
}

export interface CoinTransaction {
  id: number
  amount: number
  kind: CoinTxKind
  balance_after: number
  reason: string
  order_id: number | null
  created_at: string
  expires_at: string | null
}

export interface Reward {
  id: number
  name_he: string
  description_he: string
  cost_coins: number
  emoji: string
  is_active: boolean
}

export interface CoinRules {
  coins_per_shekel: number
  agorot_per_coin: number
  max_redeem_fraction: number
  signup_bonus_coins: number
  earn_min_order_agorot: number
  earn_percent: number
  feedback_window_hours: number
  coin_expiry_days: number
  egg_price_agorot: number
}

export interface FeedbackResult {
  ok: boolean
  coins_granted: number
  balance: number
  in_time: boolean
}

export interface AdminStats {
  total_members: number
  total_orders: number
  orders_today: number
  revenue_agorot: number
  revenue_today_agorot: number
  coins_outstanding: number
  coins_issued: number
  coins_redeemed: number
  active_orders: number
}

export interface AdminUserRow extends User {
  order_count: number
  total_spent_agorot: number
}

export interface ActivityEntry {
  id: number
  user_id: number | null
  action: string
  details: Record<string, unknown>
  created_at: string
}

export interface Paginated<T> {
  items: T[]
  total: number
  page: number
  page_size: number
}

export interface UserDetail {
  user: User
  orders: Order[]
  coin_transactions: CoinTransaction[]
  activity: ActivityEntry[]
}
