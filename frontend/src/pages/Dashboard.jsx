import { useCallback, useMemo, useState } from 'react'

import { api } from '../api/client.js'
import FiltersPanel from '../components/FiltersPanel.jsx'
import JobCard from '../components/JobCard.jsx'
import { Button, EmptyState, ErrorNote, Panel, Skeleton } from '../components/ui.jsx'
import { useApi, useStoredState } from '../hooks/useApi.js'

const DEFAULT_FILTERS = {
  category: [],
  source: [],
  seniority: [],
  format: [],
  status: [],
  min_score: 0,
  passed_filters_only: false,
  search: '',
  sort: 'score',
  limit: 25,
  offset: 0,
}

export default function Dashboard() {
  const [filters, setFilters] = useStoredState('jobfndr.filters', DEFAULT_FILTERS)
  const [scanning, setScanning] = useState(false)
  const [scanResult, setScanResult] = useState(null)
  const [scanError, setScanError] = useState(null)

  const query = useMemo(() => ({ ...DEFAULT_FILTERS, ...filters }), [filters])

  const jobs = useApi(() => api.listJobs(query), [JSON.stringify(query)])
  const categories = useApi(() => api.categories(), [])
  const sources = useApi(() => api.listSources(), [])
  const analytics = useApi(() => api.analytics(), [])

  const runScan = useCallback(async () => {
    setScanning(true)
    setScanError(null)
    setScanResult(null)
    try {
      const result = await api.scan()
      setScanResult(result)
      await Promise.all([jobs.run(), analytics.run(), sources.run()])
    } catch (err) {
      setScanError(err)
    } finally {
      setScanning(false)
    }
  }, [jobs, analytics, sources])

  const items = jobs.data?.items || []
  const total = jobs.data?.total || 0
  const hasMore = query.offset + items.length < total
  const counts = analytics.data?.category_counts

  return (
    <>
      <header className="pagehead">
        <div className="stack gap-6">
          <span className="engraved">ranked deck</span>
          <h1>Jobs</h1>
          <p className="muted" style={{ margin: 0, maxWidth: '54ch' }}>
            Remote internships, junior and mid-level roles pulled from public job
            APIs, then scored against your CV.
          </p>
        </div>

        <div className="stack gap-8" style={{ alignItems: 'flex-end' }}>
          <Button variant="primary" size="lg" onClick={runScan} disabled={scanning} loading={scanning}>
            {scanning ? 'Scanning sources…' : 'Scan jobs'}
          </Button>
          {analytics.data?.last_scan?.finished_at && !scanning && (
            <span className="engraved">
              last scan {new Date(analytics.data.last_scan.finished_at).toLocaleString()}
            </span>
          )}
        </div>
      </header>

      {scanning && (
        <Panel className="notice notice--info" style={{ marginBottom: 20 }}>
          <span className="spin" aria-hidden="true" />
          <span>
            Fetching every enabled source, then embedding and re-ranking. This
            takes a minute or two on the first run.
          </span>
        </Panel>
      )}

      {scanError && (
        <div style={{ marginBottom: 20 }}>
          <ErrorNote error={scanError} onRetry={runScan} />
        </div>
      )}

      {scanResult && !scanning && <ScanReport result={scanResult} onDismiss={() => setScanResult(null)} />}

      <div className="deck">
        <FiltersPanel
          filters={query}
          setFilters={setFilters}
          categories={categories.data || []}
          sources={sources.data || []}
          counts={counts}
          total={total}
        />

        <div className="stack gap-14">
          {jobs.error && <ErrorNote error={jobs.error} onRetry={() => jobs.run()} />}

          {jobs.loading && !items.length && <Skeleton count={5} height={124} />}

          {!jobs.loading && !items.length && !jobs.error && (
            <Panel>
              <EmptyState
                title={total === 0 && !hasActiveFilters(query) ? 'Nothing scanned yet' : 'No jobs match these filters'}
                action={
                  total === 0 && !hasActiveFilters(query) ? (
                    <Button variant="primary" onClick={runScan} disabled={scanning}>
                      Run your first scan
                    </Button>
                  ) : (
                    <Button onClick={() => setFilters(DEFAULT_FILTERS)}>Reset filters</Button>
                  )
                }
              >
                {total === 0 && !hasActiveFilters(query)
                  ? 'Scan the configured job sources to build your ranked deck. Upload your CV first for the scores to mean anything.'
                  : 'Loosen the minimum match or clear a category to see more.'}
              </EmptyState>
            </Panel>
          )}

          <div className="joblist">
            {items.map((job) => (
              <JobCard key={job.id} job={job} />
            ))}
          </div>

          {hasMore && (
            <Button
              variant="slate"
              className="btn--block"
              onClick={() => setFilters({ ...query, offset: query.offset + query.limit })}
              disabled={jobs.loading}
              loading={jobs.loading}
            >
              Load more ({total - query.offset - items.length} remaining)
            </Button>
          )}

          {query.offset > 0 && (
            <Button variant="slate" size="sm" onClick={() => setFilters({ ...query, offset: 0 })}>
              Back to top matches
            </Button>
          )}
        </div>
      </div>
    </>
  )
}

function hasActiveFilters(f) {
  return Boolean(
    f.category?.length ||
      f.source?.length ||
      f.seniority?.length ||
      f.format?.length ||
      f.status?.length ||
      f.min_score > 0 ||
      f.passed_filters_only ||
      f.search,
  )
}

function ScanReport({ result, onDismiss }) {
  const stats = result.stats || {}
  const failed = (result.per_source || []).filter((s) => s.error)

  return (
    <Panel style={{ marginBottom: 20 }}>
      <div className="panel__head">
        <div className="stack gap-4">
          <span className="engraved">scan complete</span>
          <span className="dim" style={{ fontSize: '0.82rem' }}>
            {stats.fetched || 0} fetched · {stats.new || 0} new · {stats.ranked || 0} ranked
          </span>
        </div>
        <Button size="sm" variant="slate" onClick={onDismiss}>
          Dismiss
        </Button>
      </div>
      <div className="panel__body stack gap-12">
        <div className="row wrap gap-6">
          {(result.per_source || []).map((s) => (
            <span
              key={s.source}
              className="tag"
              style={{ color: s.error ? 'var(--clay)' : 'var(--ink-soft)' }}
              title={s.error || `${s.fetched} fetched`}
            >
              {s.source} {s.error ? '·  failed' : `· ${s.fetched}`}
            </span>
          ))}
        </div>
        {failed.length > 0 && (
          <p className="dim" style={{ margin: 0, fontSize: '0.82rem' }}>
            {failed.length} source{failed.length > 1 ? 's' : ''} failed and were skipped. The
            rest of the scan completed normally.
          </p>
        )}
      </div>
    </Panel>
  )
}
