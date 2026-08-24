import { forwardRef } from 'react'

/** A raised machined panel. `well` recesses it into the deck instead. */
export function Panel({ well = false, flush = false, className = '', children, ...rest }) {
  const kind = well ? 'panel panel--well' : flush ? 'panel panel--flush' : 'panel'
  return (
    <section className={`${kind} ${className}`} {...rest}>
      {children}
    </section>
  )
}

export function PanelHead({ title, hint, children }) {
  return (
    <header className="panel__head">
      <div className="stack gap-4">
        <span className="engraved">{title}</span>
        {hint && <span className="dim" style={{ fontSize: '0.82rem' }}>{hint}</span>}
      </div>
      {children}
    </header>
  )
}

export const Button = forwardRef(function Button(
  { variant = 'default', size, active = false, loading = false, className = '', children, ...rest },
  ref,
) {
  const classes = [
    'btn',
    variant !== 'default' && `btn--${variant}`,
    size && `btn--${size}`,
    active && 'btn--on',
    className,
  ]
    .filter(Boolean)
    .join(' ')

  return (
    <button ref={ref} className={classes} aria-pressed={active || undefined} {...rest}>
      {loading && <span className="spin" aria-hidden="true" />}
      {children}
    </button>
  )
})

export function Chip({ active = false, count, children, ...rest }) {
  return (
    <button type="button" className="chip" aria-pressed={active} {...rest}>
      {children}
      {count !== undefined && <span className="chip__count mono">{count}</span>}
    </button>
  )
}

export function Toggle({ checked, onChange, label }) {
  return (
    <button
      type="button"
      className="toggle"
      role="switch"
      aria-checked={checked}
      aria-label={label}
      onClick={() => onChange(!checked)}
    />
  )
}

export function Meter({ value, max = 1, tone }) {
  const pct = max > 0 ? Math.min(100, (value / max) * 100) : 0
  return (
    <div className="meter">
      <div
        className="meter__fill"
        style={{ width: `${pct}%`, ...(tone ? { background: tone, boxShadow: `0 0 12px ${tone}55` } : {}) }}
      />
    </div>
  )
}

export function StatusDot({ status }) {
  if (!status) return null
  return (
    <span className={`status status--${status} mono`} style={{ fontSize: '0.72rem' }}>
      {status}
    </span>
  )
}

export function EmptyState({ title, children, action }) {
  return (
    <div className="empty">
      <div className="empty__ring" aria-hidden="true" />
      <h3>{title}</h3>
      {children && <p className="muted" style={{ maxWidth: '46ch' }}>{children}</p>}
      {action}
    </div>
  )
}

export function ErrorNote({ error, onRetry }) {
  if (!error) return null
  return (
    <div className="notice notice--error">
      <div className="stack gap-4 grow">
        <span className="engraved" style={{ color: 'var(--clay)' }}>error</span>
        <span>{error.message}</span>
      </div>
      {onRetry && (
        <Button size="sm" onClick={onRetry}>
          Try again
        </Button>
      )}
    </div>
  )
}

export function Skeleton({ height = 96, count = 1 }) {
  return (
    <>
      {Array.from({ length: count }, (_, i) => (
        <div key={i} className="skeleton" style={{ height }} />
      ))}
    </>
  )
}
