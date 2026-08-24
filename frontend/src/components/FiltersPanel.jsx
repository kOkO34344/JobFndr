import { Button, Chip, Panel, Toggle } from './ui.jsx'

const SENIORITY = ['internship', 'junior', 'mid-level', 'other']
const FORMATS = ['freelance', 'part-time', 'full-time', 'unknown']
const STATUSES = ['unlabeled', 'shortlisted', 'maybe', 'applied', 'rejected']
const SORTS = [
  { key: 'score', label: 'Best match' },
  { key: 'date', label: 'Newest' },
  { key: 'title', label: 'A–Z' },
]

/** Toggle a value in or out of an array filter. */
function toggle(list, value) {
  const current = list || []
  return current.includes(value) ? current.filter((v) => v !== value) : [...current, value]
}

export default function FiltersPanel({ filters, setFilters, categories, sources, counts, total }) {
  const update = (patch) => setFilters({ ...filters, ...patch, offset: 0 })
  const activeCount =
    (filters.category?.length || 0) +
    (filters.source?.length || 0) +
    (filters.seniority?.length || 0) +
    (filters.format?.length || 0) +
    (filters.status?.length || 0) +
    (filters.min_score > 0 ? 1 : 0) +
    (filters.passed_filters_only ? 1 : 0)

  return (
    <Panel className="filters">
      <div className="panel__head">
        <div className="stack gap-4">
          <span className="engraved">filters</span>
          <span className="dim" style={{ fontSize: '0.82rem' }}>
            {total} {total === 1 ? 'job' : 'jobs'} match
            {activeCount > 0 ? ` · ${activeCount} active` : ''}
          </span>
        </div>
        {activeCount > 0 && (
          <Button
            size="sm"
            variant="slate"
            onClick={() =>
              setFilters({
                ...filters,
                category: [],
                source: [],
                seniority: [],
                format: [],
                status: [],
                min_score: 0,
                passed_filters_only: false,
                search: '',
                offset: 0,
              })
            }
          >
            Clear all
          </Button>
        )}
      </div>

      <div className="panel__body stack gap-24">
        <div className="stack gap-8">
          <label className="engraved" htmlFor="job-search">
            search
          </label>
          <input
            id="job-search"
            className="field"
            type="search"
            placeholder="Title, company or description…"
            value={filters.search || ''}
            onChange={(e) => update({ search: e.target.value })}
          />
        </div>

        <FilterGroup label="category">
          {categories.map((cat) => (
            <Chip
              key={cat}
              active={filters.category?.includes(cat)}
              count={counts?.[cat]}
              onClick={() => update({ category: toggle(filters.category, cat) })}
            >
              {cat}
            </Chip>
          ))}
        </FilterGroup>

        <FilterGroup label="level">
          {SENIORITY.map((level) => (
            <Chip
              key={level}
              active={filters.seniority?.includes(level)}
              onClick={() => update({ seniority: toggle(filters.seniority, level) })}
            >
              {level}
            </Chip>
          ))}
        </FilterGroup>

        <FilterGroup label="format">
          {FORMATS.map((fmt) => (
            <Chip
              key={fmt}
              active={filters.format?.includes(fmt)}
              onClick={() => update({ format: toggle(filters.format, fmt) })}
            >
              {fmt}
            </Chip>
          ))}
        </FilterGroup>

        <FilterGroup label="my label">
          {STATUSES.map((status) => (
            <Chip
              key={status}
              active={filters.status?.includes(status)}
              onClick={() => update({ status: toggle(filters.status, status) })}
            >
              {status}
            </Chip>
          ))}
        </FilterGroup>

        {sources.length > 0 && (
          <FilterGroup label="source">
            {sources.map((src) => (
              <Chip
                key={src.name}
                active={filters.source?.includes(src.name)}
                count={src.job_count || undefined}
                onClick={() => update({ source: toggle(filters.source, src.name) })}
              >
                {src.display_name}
              </Chip>
            ))}
          </FilterGroup>
        )}

        <div className="stack gap-8">
          <div className="row between">
            <label className="engraved" htmlFor="min-score">
              minimum match
            </label>
            <span className="mono" style={{ color: 'var(--brass)' }}>
              {Math.round((filters.min_score || 0) * 100)}%
            </span>
          </div>
          <input
            id="min-score"
            className="slider"
            type="range"
            min="0"
            max="1"
            step="0.05"
            value={filters.min_score || 0}
            onChange={(e) => update({ min_score: Number(e.target.value) })}
          />
        </div>

        <div className="row between gap-16">
          <div className="stack gap-4">
            <span className="engraved">hide filtered-out</span>
            <span className="dim" style={{ fontSize: '0.8rem' }}>
              Drop non-remote and senior roles
            </span>
          </div>
          <Toggle
            checked={!!filters.passed_filters_only}
            onChange={(v) => update({ passed_filters_only: v })}
            label="Hide jobs that failed the hard filters"
          />
        </div>

        <FilterGroup label="sort by">
          {SORTS.map((sort) => (
            <Chip
              key={sort.key}
              active={filters.sort === sort.key}
              onClick={() => update({ sort: sort.key })}
            >
              {sort.label}
            </Chip>
          ))}
        </FilterGroup>
      </div>
    </Panel>
  )
}

function FilterGroup({ label, children }) {
  return (
    <div className="stack gap-8">
      <span className="engraved">{label}</span>
      <div className="row wrap gap-6">{children}</div>
    </div>
  )
}
