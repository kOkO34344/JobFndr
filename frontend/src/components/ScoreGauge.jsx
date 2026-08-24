import { useEffect, useRef, useState } from 'react'

/**
 * The match score as an inset brass gauge — the app's signature readout.
 *
 * A dial rather than a number because the score is a continuous reading off an
 * instrument, and the eye compares arcs across a list far faster than digits.
 * The needle sweeps up once on mount, the way a real meter settles.
 */
export default function ScoreGauge({ value = 0, size = 74, label = 'match', filtered = false }) {
  const [shown, setShown] = useState(0)
  const raf = useRef(null)

  useEffect(() => {
    const target = Math.max(0, Math.min(1, value || 0))
    const reduce = window.matchMedia?.('(prefers-reduced-motion: reduce)').matches
    if (reduce) {
      setShown(target)
      return
    }
    const start = performance.now()
    const duration = 620
    const tick = (now) => {
      const t = Math.min(1, (now - start) / duration)
      const eased = 1 - Math.pow(1 - t, 3)
      setShown(target * eased)
      if (t < 1) raf.current = requestAnimationFrame(tick)
    }
    raf.current = requestAnimationFrame(tick)
    return () => raf.current && cancelAnimationFrame(raf.current)
  }, [value])

  const stroke = Math.max(5, size * 0.085)
  const radius = (size - stroke) / 2
  const centre = size / 2
  // A 270° sweep, opening at the bottom, reads as a gauge; a full ring reads
  // as a progress spinner.
  const sweep = 270
  const circumference = 2 * Math.PI * radius
  const arcLength = (sweep / 360) * circumference

  const tone = filtered
    ? 'var(--clay)'
    : shown >= 0.7
      ? 'var(--mint)'
      : shown >= 0.45
        ? 'var(--brass)'
        : 'var(--slate)'

  const pct = Math.round((value || 0) * 100)

  return (
    <div
      className="gauge"
      style={{ width: size, height: size }}
      role="img"
      aria-label={`${label}: ${pct} percent`}
    >
      <svg width={size} height={size} style={{ transform: 'rotate(135deg)' }} aria-hidden="true">
        <circle
          cx={centre}
          cy={centre}
          r={radius}
          fill="none"
          stroke="rgba(0,0,0,0.45)"
          strokeWidth={stroke}
          strokeLinecap="round"
          strokeDasharray={`${arcLength} ${circumference}`}
        />
        <circle
          cx={centre}
          cy={centre}
          r={radius}
          fill="none"
          stroke={tone}
          strokeWidth={stroke}
          strokeLinecap="round"
          strokeDasharray={`${arcLength * shown} ${circumference}`}
          style={{ filter: `drop-shadow(0 0 6px ${tone})` }}
        />
      </svg>
      <div className="gauge__readout">
        <span className="gauge__value mono" style={{ fontSize: size * 0.26 }}>
          {pct}
        </span>
        <span className="gauge__label engraved" style={{ fontSize: size * 0.1 }}>
          {label}
        </span>
      </div>
    </div>
  )
}
