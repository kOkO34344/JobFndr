import { useCallback } from 'react'
import { Link, useNavigate, useParams } from 'react-router-dom'

import { api } from '../api/client.js'
import ScoreGauge from '../components/ScoreGauge.jsx'
import { Button, ErrorNote, Meter, Panel, PanelHead, Skeleton } from '../components/ui.jsx'
import { useApi } from '../hooks/useApi.js'

const LABELS = [
  { status: 'shortlisted', label: 'Shortlist', variant: 'mint' },
  { status: 'maybe', label: 'Maybe later', variant: 'slate' },
  { status: 'applied', label: 'Mark applied', variant: 'primary' },
  { status: 'rejected', label: 'Reject', variant: 'clay' },
]

export default function JobDetail() {
  const { id } = useParams()
  const navigate = useNavigate()
  const job = useApi(() => api.getJob(id), [id])

  const setLabel = useCallback(
    async (status) => {
      const current = job.data?.label?.status
      // Clicking the active label again clears it, so triage is reversible.
      const updated = current === status ? await api.clearLabel(id) : await api.labelJob(id, status)
      job.setData(updated)
    },
    [id, job],
  )

  if (job.loading && !job.data) return <Skeleton count={2} height={220} />
  if (job.error) return <ErrorNote error={job.error} onRetry={() => job.run()} />
  if (!job.data) return null

  const j = job.data
  const explanation = j.match?.explanation || {}
  const components = explanation.components || {}
  const weights = explanation.component_weights || {}
  const currentLabel = j.label?.status

  return (
    <>
      <header className="pagehead">
        <div className="stack gap-6" style={{ minWidth: 0 }}>
          <Link to="/" className="engraved">
            ← back to deck
          </Link>
          <h1>{j.title}</h1>
          <div className="row wrap gap-8 muted">
            <strong style={{ color: 'var(--ink)' }}>{j.company || 'Unlisted company'}</strong>
            <span className="dim">·</span>
            <span>{j.location || 'Remote'}</span>
            <span className="dim">·</span>
            <span className="mono dim">{j.source}</span>
          </div>
        </div>
        <ScoreGauge value={j.final_score ?? 0} size={104} filtered={j.passed_filters === false} />
      </header>

      <div className="detail">
        <div className="stack gap-20">
          <Panel>
            <PanelHead title="why this matches you" />
            <div className="panel__body stack gap-20">
              {explanation.summary && <p style={{ margin: 0 }}>{explanation.summary}</p>}

              {explanation.filters?.passed === false && (
                <div className="notice notice--error">
                  <div className="stack gap-4">
                    <span className="engraved" style={{ color: 'var(--clay)' }}>
                      failed hard filters
                    </span>
                    <span>{explanation.filters.reasons?.join(' · ')}</span>
                  </div>
                </div>
              )}

              {explanation.matched_domains?.length > 0 && (
                <div className="stack gap-10">
                  <span className="engraved">domain overlap</span>
                  {explanation.matched_domains.map((d) => (
                    <div key={d.key} className="stack gap-6">
                      <div className="row between" style={{ fontSize: '0.86rem' }}>
                        <span>{d.label}</span>
                        <span className="mono dim">
                          job {Math.round(d.job_score * 100)}% · you {Math.round(d.profile_weight * 100)}%
                        </span>
                      </div>
                      <Meter value={d.contribution} max={1} />
                    </div>
                  ))}
                </div>
              )}

              {explanation.matched_skills?.length > 0 && (
                <div className="stack gap-8">
                  <span className="engraved">your skills in this posting</span>
                  <div className="row wrap gap-6">
                    {explanation.matched_skills.map((skill) => (
                      <span key={skill} className="tag" style={{ color: 'var(--mint)' }}>
                        {skill}
                      </span>
                    ))}
                  </div>
                </div>
              )}

              <div className="stack gap-8">
                <span className="engraved">score breakdown</span>
                <div className="breakdown">
                  {Object.entries(components).map(([key, value]) => (
                    <div key={key} className="breakdown__row">
                      <span className="mono dim">{key}</span>
                      <Meter value={value} max={1} />
                      <span className="mono">{Math.round(value * 100)}%</span>
                      {weights[key] !== undefined && (
                        <span className="mono dim" style={{ fontSize: '0.7rem' }}>
                          ×{weights[key]}
                        </span>
                      )}
                    </div>
                  ))}
                </div>
                <div className="row wrap gap-16 dim mono" style={{ fontSize: '0.75rem' }}>
                  <span>rule {Math.round((j.match?.rule_score ?? 0) * 100)}%</span>
                  <span>semantic {Math.round((j.match?.semantic_score ?? 0) * 100)}%</span>
                  <span>
                    weights {explanation.weights?.rule} / {explanation.weights?.semantic}
                  </span>
                </div>
              </div>
            </div>
          </Panel>

          <Panel>
            <PanelHead title="full description" />
            <div className="panel__body">
              <pre className="description">{j.raw_description || 'No description provided.'}</pre>
            </div>
          </Panel>
        </div>

        <div className="stack gap-20">
          <Panel>
            <PanelHead title="triage" hint={currentLabel ? `Currently ${currentLabel}` : 'Not yet labelled'} />
            <div className="panel__body stack gap-10">
              {LABELS.map((l) => (
                <Button
                  key={l.status}
                  variant={l.variant}
                  className="btn--block"
                  active={currentLabel === l.status}
                  onClick={() => setLabel(l.status)}
                >
                  {currentLabel === l.status ? `${l.label} ✓` : l.label}
                </Button>
              ))}
              <Button
                variant="primary"
                className="btn--block"
                onClick={() => navigate(`/jobs/${id}/proposal`)}
              >
                Draft proposal
              </Button>
            </div>
          </Panel>

          <Panel>
            <PanelHead title="posting details" />
            <div className="panel__body stack gap-12">
              <Detail label="category" value={j.category} />
              <Detail label="level" value={j.seniority} />
              <Detail label="format" value={j.format} />
              <Detail label="remote" value={j.remote_flag ? 'yes' : 'no'} />
              {j.salary_text && <Detail label="pay" value={j.salary_text} />}
              <Detail
                label="posted"
                value={j.posted_at ? new Date(j.posted_at).toLocaleDateString() : 'unknown'}
              />
              <Detail label="source" value={j.source_display_name || j.source} />
              <a className="btn btn--block" href={j.url} target="_blank" rel="noopener noreferrer">
                Open original posting ↗
              </a>
              {j.source_attribution && (
                <p className="dim" style={{ margin: 0, fontSize: '0.74rem' }}>
                  {j.source_attribution}
                </p>
              )}
            </div>
          </Panel>

          {j.tags?.length > 0 && (
            <Panel>
              <PanelHead title="tags" />
              <div className="panel__body row wrap gap-6">
                {j.tags.map((tag) => (
                  <span key={tag} className="tag">
                    {tag}
                  </span>
                ))}
              </div>
            </Panel>
          )}
        </div>
      </div>
    </>
  )
}

function Detail({ label, value }) {
  return (
    <div className="row between gap-12">
      <span className="engraved">{label}</span>
      <span className="mono" style={{ fontSize: '0.82rem' }}>
        {value}
      </span>
    </div>
  )
}
