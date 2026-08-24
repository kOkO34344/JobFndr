import { Link } from 'react-router-dom'

import ScoreGauge from './ScoreGauge.jsx'
import { StatusDot } from './ui.jsx'

const CATEGORY_TONE = {
  Internships: 'var(--brass)',
  'Freelance gigs': 'var(--mint)',
  'Part-time remote': 'var(--slate)',
  'Full-time remote': 'var(--violet)',
  'AI & Coding': 'var(--brass-bright)',
  'Trust & Safety': 'var(--mint)',
  'Political/Policy': 'var(--violet)',
  Markets: 'var(--brass)',
  'Admin/Support': 'var(--slate)',
}

function relativeDate(value) {
  if (!value) return null
  const days = Math.floor((Date.now() - new Date(value).getTime()) / 86400000)
  if (Number.isNaN(days)) return null
  if (days <= 0) return 'today'
  if (days === 1) return 'yesterday'
  if (days < 30) return `${days}d ago`
  return `${Math.floor(days / 30)}mo ago`
}

export default function JobCard({ job }) {
  const posted = relativeDate(job.posted_at)
  const tone = CATEGORY_TONE[job.category] || 'var(--slate)'

  return (
    <Link to={`/jobs/${job.id}`} className="jobcard panel" aria-label={`${job.title} at ${job.company || 'unknown company'}`}>
      <ScoreGauge value={job.final_score ?? 0} filtered={job.passed_filters === false} />

      <div className="grow stack gap-8">
        <div className="row between gap-12">
          <h3 className="jobcard__title">{job.title}</h3>
          <StatusDot status={job.status} />
        </div>

        <div className="row wrap gap-8 muted" style={{ fontSize: '0.86rem' }}>
          <strong style={{ color: 'var(--ink)', fontWeight: 500 }}>
            {job.company || 'Unlisted company'}
          </strong>
          <span className="dim">·</span>
          <span>{job.location || 'Remote'}</span>
          {posted && (
            <>
              <span className="dim">·</span>
              <span className="mono dim">{posted}</span>
            </>
          )}
        </div>

        {job.match_summary && <p className="jobcard__summary">{job.match_summary}</p>}

        <div className="row wrap gap-6">
          <span className="tag" style={{ color: tone }}>
            {job.category}
          </span>
          <span className="tag">{job.seniority}</span>
          <span className="tag">{job.format}</span>
          <span className="tag dim">{job.source}</span>
          {job.passed_filters === false && (
            <span className="tag" style={{ color: 'var(--clay)' }}>
              filtered
            </span>
          )}
        </div>
      </div>
    </Link>
  )
}
