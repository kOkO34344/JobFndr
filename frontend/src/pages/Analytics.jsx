import { api } from '../api/client.js'
import { Button, ErrorNote, Meter, Panel, PanelHead, Skeleton } from '../components/ui.jsx'
import { useApi } from '../hooks/useApi.js'

// Reserved status tokens, in the order they are always displayed.
const LABEL_ORDER = [
  { key: 'shortlisted', tone: 'var(--sig-good)' },
  { key: 'maybe', tone: 'var(--sig-hold)' },
  { key: 'applied', tone: 'var(--sig-sent)' },
  { key: 'rejected', tone: 'var(--sig-stop)' },
]

const BUCKETS = [
  { key: 'strong', label: 'Strong', range: '70–100%' },
  { key: 'good', label: 'Good', range: '50–69%' },
  { key: 'weak', label: 'Weak', range: '30–49%' },
  { key: 'poor', label: 'Poor', range: 'below 30%' },
]

export default function Analytics() {
  const analytics = useApi(() => api.analytics(), [])

  if (analytics.loading && !analytics.data) return <Skeleton count={3} height={170} />
  if (analytics.error) return <ErrorNote error={analytics.error} onRetry={() => analytics.run()} />

  const a = analytics.data
  const labels = a.label_counts || {}
  const triaged = LABEL_ORDER.reduce((sum, l) => sum + (labels[l.key] || 0), 0)
  const highMatch = a.high_match_by_category || {}
  const highTotal = Object.values(highMatch).reduce((s, n) => s + n, 0)

  return (
    <>
      <header className="pagehead">
        <div className="stack gap-6">
          <span className="engraved">pipeline readout</span>
          <h1>Analytics</h1>
          <p className="muted" style={{ margin: 0, maxWidth: '54ch' }}>
            What the last scan surfaced, and what you have done with it.
          </p>
        </div>
        <Button onClick={() => analytics.run()} loading={analytics.loading}>
          Refresh
        </Button>
      </header>

      <div className="tiles">
        <StatTile label="jobs stored" value={a.total_jobs} />
        <StatTile label="strong matches" value={a.score_buckets?.strong ?? 0} hint="70% and above" />
        <StatTile label="triaged" value={triaged} hint={`of ${a.total_jobs}`} />
        <StatTile
          label="shortlisted"
          value={labels.shortlisted || 0}
          tone="var(--sig-good)"
        />
      </div>

      <div className="detail" style={{ marginTop: 24 }}>
        <div className="stack gap-20">
          <Panel>
            <PanelHead
              title="high matches by category"
              hint="Jobs scoring 50% or more that passed the hard filters"
            />
            <div className="panel__body">
              {highTotal === 0 ? (
                <p className="dim" style={{ margin: 0 }}>
                  No jobs above 50% yet. Run a scan, or upload your CV so semantic
                  scoring has something to compare against.
                </p>
              ) : (
                <BarList
                  rows={Object.entries(highMatch).sort((x, y) => y[1] - x[1])}
                  max={Math.max(...Object.values(highMatch))}
                  unit="jobs"
                />
              )}
            </div>
          </Panel>

          <Panel>
            <PanelHead title="everything scanned, by category" />
            <div className="panel__body">
              {Object.keys(a.category_counts || {}).length === 0 ? (
                <p className="dim" style={{ margin: 0 }}>Nothing scanned yet.</p>
              ) : (
                <BarList
                  rows={Object.entries(a.category_counts).sort((x, y) => y[1] - x[1])}
                  max={Math.max(...Object.values(a.category_counts))}
                  unit="jobs"
                />
              )}
            </div>
          </Panel>
        </div>

        <div className="stack gap-20">
          <Panel>
            <PanelHead title="your decisions" hint={`${triaged} labelled`} />
            <div className="panel__body stack gap-14">
              {triaged === 0 ? (
                <p className="dim" style={{ margin: 0, fontSize: '0.86rem' }}>
                  Open a job and shortlist, hold, apply or reject it to start
                  building this readout.
                </p>
              ) : (
                LABEL_ORDER.map(({ key, tone }) => (
                  <div key={key} className="stack gap-6">
                    <div className="row between" style={{ fontSize: '0.86rem' }}>
                      <span className={`status status--${key}`}>{key}</span>
                      <span className="mono">{labels[key] || 0}</span>
                    </div>
                    <Meter value={labels[key] || 0} max={triaged} tone={tone} />
                  </div>
                ))
              )}
            </div>
          </Panel>

          <Panel>
            <PanelHead title="match quality" hint="Every scored job" />
            <div className="panel__body stack gap-14">
              {BUCKETS.map((b) => {
                const value = a.score_buckets?.[b.key] ?? 0
                return (
                  <div key={b.key} className="stack gap-6">
                    <div className="row between" style={{ fontSize: '0.86rem' }}>
                      <span>
                        {b.label} <span className="dim mono" style={{ fontSize: '0.74rem' }}>{b.range}</span>
                      </span>
                      <span className="mono">{value}</span>
                    </div>
                    <Meter value={value} max={a.total_jobs || 1} />
                  </div>
                )
              })}
            </div>
          </Panel>

          <Panel>
            <PanelHead title="sources" />
            <div className="panel__body stack gap-10">
              {Object.entries(a.source_counts || {})
                .sort((x, y) => y[1] - x[1])
                .map(([name, count]) => (
                  <div key={name} className="row between" style={{ fontSize: '0.86rem' }}>
                    <span className="truncate">{name}</span>
                    <span className="mono dim">{count}</span>
                  </div>
                ))}
              {!Object.keys(a.source_counts || {}).length && (
                <span className="dim" style={{ fontSize: '0.86rem' }}>No jobs yet.</span>
              )}
            </div>
          </Panel>

          {a.last_scan && (
            <Panel>
              <PanelHead title="last scan" />
              <div className="panel__body stack gap-8" style={{ fontSize: '0.85rem' }}>
                <Row label="status" value={a.last_scan.status} />
                <Row label="fetched" value={a.last_scan.jobs_fetched} />
                <Row label="new" value={a.last_scan.jobs_new} />
                <Row label="ranked" value={a.last_scan.jobs_ranked} />
                <Row
                  label="finished"
                  value={
                    a.last_scan.finished_at
                      ? new Date(a.last_scan.finished_at).toLocaleString()
                      : 'still running'
                  }
                />
                {a.last_scan.errors?.length > 0 && (
                  <p className="dim" style={{ margin: '4px 0 0', fontSize: '0.8rem' }}>
                    {a.last_scan.errors.length} source
                    {a.last_scan.errors.length > 1 ? 's' : ''} failed and were skipped.
                  </p>
                )}
              </div>
            </Panel>
          )}
        </div>
      </div>
    </>
  )
}

/**
 * Horizontal bars: category names are long and the job is magnitude
 * comparison, so bars beat a pie or a column chart. One hue (magnitude is
 * sequential, not categorical) with the value labelled directly on every row,
 * which doubles as the table view.
 */
function BarList({ rows, max, unit }) {
  return (
    <div className="barlist">
      {rows.map(([name, value]) => (
        <div key={name} className="barlist__row" title={`${name}: ${value} ${unit}`}>
          <span className="barlist__name truncate">{name}</span>
          <Meter value={value} max={max} />
          <span className="mono barlist__value">{value}</span>
        </div>
      ))}
    </div>
  )
}

function StatTile({ label, value, hint, tone }) {
  return (
    <Panel className="tile">
      <span className="engraved">{label}</span>
      <span className="tile__value mono" style={tone ? { color: tone } : undefined}>
        {value}
      </span>
      {hint && <span className="dim" style={{ fontSize: '0.76rem' }}>{hint}</span>}
    </Panel>
  )
}

function Row({ label, value }) {
  return (
    <div className="row between gap-12">
      <span className="engraved">{label}</span>
      <span className="mono">{value}</span>
    </div>
  )
}
