/**
 * The Poet Coin symbol: a chickpea, drawn as inline SVG so it scales and
 * inherits currentColor-independent brand tones.
 */
export function Chickpea({ className = 'w-5 h-5' }: { className?: string }) {
  return (
    <svg viewBox="0 0 32 32" className={className} aria-hidden="true">
      <defs>
        <radialGradient id="pc-g" cx="35%" cy="30%" r="75%">
          <stop offset="0%" stopColor="#F2DFA4" />
          <stop offset="55%" stopColor="#DFAF55" />
          <stop offset="100%" stopColor="#B07F2C" />
        </radialGradient>
      </defs>
      {/* Chickpea body: round with the characteristic little beak. */}
      <path
        d="M16 3.6c6.1 0 11.2 4.8 11.2 11.3 0 6.8-4.7 12.2-10.5 13.4-1 .2-1.7-.5-1.5-1.4.3-1.4.9-2.6 1.9-3.7.5-.6.2-1.3-.6-1.2-5.9.6-11.7-4-11.7-10.4C4.8 7.4 9.9 3.6 16 3.6Z"
        fill="url(#pc-g)"
        stroke="#8A6220"
        strokeWidth="1.3"
        strokeLinejoin="round"
      />
      <ellipse cx="12.2" cy="11.4" rx="2.6" ry="1.9" fill="#F7EBC4" opacity=".55" />
      <circle cx="19.4" cy="16.6" r=".9" fill="#8A6220" opacity=".35" />
      <circle cx="14.6" cy="18.4" r=".7" fill="#8A6220" opacity=".3" />
    </svg>
  )
}

/** Coin balance pill: chickpea + amount. */
export function CoinAmount({
  value,
  className = '',
  size = 'md',
  signed = false,
}: {
  value: number
  className?: string
  size?: 'sm' | 'md' | 'lg'
  signed?: boolean
}) {
  const dims = { sm: 'w-4 h-4', md: 'w-5 h-5', lg: 'w-7 h-7' }[size]
  const text = { sm: 'text-sm', md: 'text-base', lg: 'text-2xl' }[size]
  const prefix = signed && value > 0 ? '+' : ''
  return (
    <span className={`inline-flex items-center gap-1.5 font-bold tabular-nums ${text} ${className}`}>
      <Chickpea className={dims} />
      {prefix}
      {value.toLocaleString('he-IL')}
    </span>
  )
}
