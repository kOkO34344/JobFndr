import { useEffect, useRef, useState } from 'react'

import { api } from '../api/client.js'
import { Button, ErrorNote, Panel, PanelHead, Skeleton, Toggle } from '../components/ui.jsx'
import { useApi } from '../hooks/useApi.js'

const SENIORITY = ['internship', 'junior', 'mid-level', 'senior', 'other']
const FORMATS = ['freelance', 'part-time', 'full-time', 'unknown']

export default function ProfileSettings() {
  const profile = useApi(() => api.getProfile(), [])
  const sources = useApi(() => api.listSources(), [])
  const [draft, setDraft] = useState(null)
  const [saving, setSaving] = useState(false)
  const [saveError, setSaveError] = useState(null)
  const [saved, setSaved] = useState(false)
  const [uploading, setUploading] = useState(false)
  const [uploadError, setUploadError] = useState(null)
  const [warnings, setWarnings] = useState([])
  const fileInput = useRef(null)

  useEffect(() => {
    if (profile.data && !draft) setDraft(profile.data)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [profile.data])

  const update = (patch) => {
    setDraft((d) => ({ ...d, ...patch }))
    setSaved(false)
  }

  const toggleIn = (key, value) => {
    const list = draft[key] || []
    update({ [key]: list.includes(value) ? list.filter((v) => v !== value) : [...list, value] })
  }

  const save = async () => {
    setSaving(true)
    setSaveError(null)
    try {
      const updated = await api.updateProfile({
        name: draft.name,
        email: draft.email,
        location: draft.location,
        headline: draft.headline,
        skills: draft.skills,
        preferred_roles: draft.preferred_roles,
        preferred_formats: draft.preferred_formats,
        preferred_seniority: draft.preferred_seniority,
        domains: draft.domains,
        remote_only: draft.remote_only,
        reembed: true,
      })
      profile.setData(updated)
      setDraft(updated)
      setSaved(true)
    } catch (err) {
      setSaveError(err)
    } finally {
      setSaving(false)
    }
  }

  const upload = async (file) => {
    if (!file) return
    setUploading(true)
    setUploadError(null)
    setWarnings([])
    try {
      const result = await api.uploadCv(file)
      profile.setData(result.profile)
      setDraft(result.profile)
      setWarnings(result.warnings || [])
    } catch (err) {
      setUploadError(err)
    } finally {
      setUploading(false)
      if (fileInput.current) fileInput.current.value = ''
    }
  }

  if (profile.loading && !draft) return <Skeleton count={3} height={180} />
  if (profile.error) return <ErrorNote error={profile.error} onRetry={() => profile.run()} />
  if (!draft) return null

  return (
    <>
      <header className="pagehead">
        <div className="stack gap-6">
          <span className="engraved">operator profile</span>
          <h1>Profile</h1>
          <p className="muted" style={{ margin: 0, maxWidth: '56ch' }}>
            Everything here feeds the ranker. Saving re-embeds your profile and
            re-scores every stored job.
          </p>
        </div>
        <div className="stack gap-8" style={{ alignItems: 'flex-end' }}>
          <Button variant="primary" size="lg" onClick={save} disabled={saving} loading={saving}>
            {saving ? 'Saving & re-ranking…' : saved ? 'Saved ✓' : 'Save & re-rank'}
          </Button>
          {saveError && <span style={{ color: 'var(--clay)', fontSize: '0.82rem' }}>{saveError.message}</span>}
        </div>
      </header>

      <div className="detail">
        <div className="stack gap-20">
          <Panel>
            <PanelHead
              title="cv"
              hint={draft.has_cv ? 'Parsed and embedded' : 'No CV uploaded yet'}
            />
            <div className="panel__body stack gap-14">
              {uploadError && <ErrorNote error={uploadError} />}

              <div className="row wrap gap-12 between">
                <div className="stack gap-4">
                  <span style={{ fontSize: '0.9rem' }}>
                    {draft.has_cv ? 'Upload a new PDF to re-parse your profile' : 'Upload your CV as a PDF'}
                  </span>
                  <span className="dim" style={{ fontSize: '0.8rem' }}>
                    Manually added experience is kept when you re-upload.
                  </span>
                </div>
                <input
                  ref={fileInput}
                  type="file"
                  accept="application/pdf,.pdf"
                  className="sr-only"
                  id="cv-file"
                  onChange={(e) => upload(e.target.files?.[0])}
                />
                <Button
                  variant="primary"
                  onClick={() => fileInput.current?.click()}
                  disabled={uploading}
                  loading={uploading}
                >
                  {uploading ? 'Parsing…' : 'Choose PDF'}
                </Button>
              </div>

              {warnings.length > 0 && (
                <div className="notice notice--info">
                  <div className="stack gap-4">
                    <span className="engraved">parsed with gaps</span>
                    {warnings.map((w) => (
                      <span key={w} style={{ fontSize: '0.85rem' }}>
                        {w}
                      </span>
                    ))}
                  </div>
                </div>
              )}

              <div className="row wrap gap-16 engraved divide-above">
                <span>cv text {draft.has_cv ? 'stored' : 'missing'}</span>
                <span>embedding {draft.has_embedding ? 'ready' : 'missing'}</span>
              </div>
            </div>
          </Panel>

          <Panel>
            <PanelHead title="identity" />
            <div className="panel__body stack gap-14">
              <Field label="name" value={draft.name || ''} onChange={(v) => update({ name: v })} />
              <Field label="email" value={draft.email || ''} onChange={(v) => update({ email: v })} />
              <Field label="location" value={draft.location || ''} onChange={(v) => update({ location: v })} />
              <div className="stack gap-8">
                <span className="engraved">headline</span>
                <textarea
                  className="field"
                  style={{ minHeight: 90 }}
                  value={draft.headline || ''}
                  onChange={(e) => update({ headline: e.target.value })}
                />
              </div>
            </div>
          </Panel>

          <Panel>
            <PanelHead title="skills" hint="Matched literally against posting text" />
            <div className="panel__body stack gap-12">
              <TokenEditor
                values={draft.skills || []}
                onChange={(skills) => update({ skills })}
                placeholder="Add a skill and press Enter"
              />
            </div>
          </Panel>

          <Panel>
            <PanelHead title="roles you want" hint="Used as context when drafting proposals" />
            <div className="panel__body">
              <TokenEditor
                values={draft.preferred_roles || []}
                onChange={(preferred_roles) => update({ preferred_roles })}
                placeholder="Add a target role and press Enter"
              />
            </div>
          </Panel>
        </div>

        <div className="stack gap-20">
          <Panel>
            <PanelHead title="hard filters" />
            <div className="panel__body stack gap-20">
              <div className="row between gap-12 divide-below">
                <div className="stack gap-4">
                  <span style={{ fontSize: '0.9rem' }}>Remote only</span>
                  <span className="dim" style={{ fontSize: '0.8rem' }}>
                    Reject anything on-site or hybrid
                  </span>
                </div>
                <Toggle
                  checked={!!draft.remote_only}
                  onChange={(v) => update({ remote_only: v })}
                  label="Remote only"
                />
              </div>

              <div className="stack gap-8">
                <span className="engraved">levels</span>
                <div className="row wrap gap-6">
                  {SENIORITY.map((s) => (
                    <button
                      key={s}
                      type="button"
                      className="chip"
                      aria-pressed={draft.preferred_seniority?.includes(s)}
                      onClick={() => toggleIn('preferred_seniority', s)}
                    >
                      {s}
                    </button>
                  ))}
                </div>
              </div>

              <div className="stack gap-8">
                <span className="engraved">formats</span>
                <div className="row wrap gap-6">
                  {FORMATS.map((f) => (
                    <button
                      key={f}
                      type="button"
                      className="chip"
                      aria-pressed={draft.preferred_formats?.includes(f)}
                      onClick={() => toggleIn('preferred_formats', f)}
                    >
                      {f}
                    </button>
                  ))}
                </div>
              </div>
            </div>
          </Panel>

          <Panel>
            <PanelHead title="domain weights" hint="How much each domain pulls a job up" />
            <div className="panel__body stack gap-14">
              {(draft.domains || []).map((d, i) => (
                <div key={d.key} className="stack gap-6">
                  <div className="row between">
                    <span style={{ fontSize: '0.86rem' }}>{d.label}</span>
                    <span className="mono" style={{ color: 'var(--brass)' }}>
                      {Math.round((d.weight ?? 0) * 100)}%
                    </span>
                  </div>
                  <input
                    className="slider"
                    type="range"
                    min="0"
                    max="1"
                    step="0.05"
                    value={d.weight ?? 0}
                    aria-label={`${d.label} weight`}
                    onChange={(e) => {
                      const domains = [...draft.domains]
                      domains[i] = { ...d, weight: Number(e.target.value) }
                      update({ domains })
                    }}
                  />
                </div>
              ))}
              {!draft.domains?.length && (
                <p className="dim" style={{ margin: 0, fontSize: '0.85rem' }}>
                  Upload your CV to derive domain weights.
                </p>
              )}
            </div>
          </Panel>

          <Panel>
            <PanelHead title="experience" hint="From your CV, plus anything added by hand" />
            <div className="panel__body stack gap-12">
              {(draft.experience || []).map((e, i) => (
                <div key={`${e.role}-${i}`} className="stack gap-4">
                  <span style={{ fontSize: '0.9rem' }}>{e.role}</span>
                  <span className="dim" style={{ fontSize: '0.82rem' }}>
                    {[e.company, e.dates].filter(Boolean).join(' · ')}
                    {e.source === 'manual' && ' · added manually'}
                  </span>
                </div>
              ))}
              {!draft.experience?.length && (
                <p className="dim" style={{ margin: 0, fontSize: '0.85rem' }}>
                  No experience parsed yet.
                </p>
              )}
            </div>
          </Panel>

          <Panel>
            <PanelHead title="sources" hint="Toggle which boards a scan hits" />
            <div className="panel__body stack gap-10">
              {(sources.data || []).map((s) => (
                <div key={s.name} className="row between gap-12">
                  <div className="stack gap-4" style={{ minWidth: 0 }}>
                    <span className="truncate" style={{ fontSize: '0.88rem' }}>
                      {s.display_name}
                    </span>
                    <span className="dim mono" style={{ fontSize: '0.72rem' }}>
                      {s.type} · {s.job_count} jobs
                    </span>
                  </div>
                  <Toggle
                    checked={s.enabled}
                    label={`Enable ${s.display_name}`}
                    onChange={async (v) => {
                      await api.toggleSource(s.name, v)
                      sources.run()
                    }}
                  />
                </div>
              ))}
            </div>
          </Panel>
        </div>
      </div>
    </>
  )
}

function Field({ label, value, onChange }) {
  return (
    <div className="stack gap-8">
      <span className="engraved">{label}</span>
      <input className="field" value={value} onChange={(e) => onChange(e.target.value)} />
    </div>
  )
}

/** Add/remove chips for a list of free-text values. */
function TokenEditor({ values, onChange, placeholder }) {
  const [entry, setEntry] = useState('')

  const add = () => {
    const value = entry.trim()
    if (value && !values.includes(value)) onChange([...values, value])
    setEntry('')
  }

  return (
    <div className="stack gap-12">
      <div className="row wrap gap-6">
        {values.map((v) => (
          <button
            key={v}
            type="button"
            className="chip"
            onClick={() => onChange(values.filter((x) => x !== v))}
            title={`Remove ${v}`}
          >
            {v} <span className="dim">×</span>
          </button>
        ))}
        {!values.length && <span className="dim" style={{ fontSize: '0.85rem' }}>Nothing yet.</span>}
      </div>
      <div className="row gap-8">
        <input
          className="field"
          value={entry}
          placeholder={placeholder}
          onChange={(e) => setEntry(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === 'Enter') {
              e.preventDefault()
              add()
            }
          }}
        />
        <Button size="sm" onClick={add} disabled={!entry.trim()}>
          Add
        </Button>
      </div>
    </div>
  )
}
