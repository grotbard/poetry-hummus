export function Logo({ className = 'w-12 h-12' }: { className?: string }) {
  return (
    <img
      src="/logo.jpg"
      alt="חומוס המשורר"
      className={`${className} rounded-2xl object-cover shadow-plate`}
    />
  )
}
