import { useEffect, useState } from 'react'
import { Link, useParams } from 'react-router-dom'

import { api } from '../api/client.js'
import { Button, ErrorNote, Panel, PanelHead, Skeleton } from '../components/ui.jsx'
import { useApi, useStoredState } from '../hooks/useApi.js'

const TONES = [
  { key: 'professional', label: 'Professional' },
  { key: 'warm', label: 'Warm' },
  { key: 'direct', label: 'Direct' },
  { key: 'enthusiastic', label: 'Enthusiastic' },
]

export default function ProposalDraft() {
  const { id } = useParams()
  const [tone, setTone] = useStoredState('jobfndr.tone', 'professional')
  const [instructions, setInstructions] = useState('')
  const [text, setText] = useState('')
  const [meta, setMeta] = useState(null)
  const [generating, setGenerating] = useState(false)
  const [genError, setGenError] = useState(null)
  const [copied, setCopied] = useState(false)

  const job = useApi(() => api.getJob(id), [id])
  const existing = useApi(() => api.latestProposal(id), [id])

  // Seed the editor from the last saved draft rather than an empty box.
  useEffect(() => {
    if (existing.data?.content && !text) {
      setText(existing.data.content)
      setMeta({ generated_by: existing.data.generated_by, model: existing.data.model_used })
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [existing.data])

  const generate = async () => {
    setGenerating(true)
    setGenError(null)
    try {
      const result = await api.createProposal(id, { tone, extra_instructions: instructions || null })
      setText(result.proposal.content)
      setMeta({
        generated_by: result.proposal.generated_by,
        model: result.proposal.model_used,
        ...result.meta,
      })
    } catch (err) {
      setGenError(err)
    } finally {
      setGenerating(false)
    }
  }

  const copy = async () => {
    try {
      await navigator.clipboard.writeText(text)
    } catch {
      // Clipboard API needs a secure context; select the textarea instead.
      const area = document.getElementById('proposal-editor')
      area?.select()
      document.execCommand?.('copy')
    }
    setCopied(true)
    setTimeout(() => setCopied(false), 2200)
  }

  if (job.loading && !job.data) return <Skeleton count={2} height={200} />
  if (job.error) return <ErrorNote error={job.error} onRetry={() => job.run()} />

  const j = job.data
  const words = text.trim() ? text.trim().split(/\s+/).length : 0

  return (
    <>
      <header className="pagehead">
        <div className="stack gap-6">
          <Link to={`/jobs/${id}`} className="engraved">
            ← back to job
          </Link>
          <h1>Draft proposal</h1>
          <p className="muted" style={{ margin: 0 }}>
            {j?.title} · {j?.company || 'Unlisted company'}
          </p>
        </div>
        <Button variant="primary" size="lg" onClick={generate} disabled={generating} loading={generating}>
          {generating ? 'Writing…' : text ? 'Regenerate' : 'Generate draft'}
        </Button>
      </header>

      <div className="detail">
        <Panel>
          <div className="panel__head">
            <div className="stack gap-4">
              <span className="engraved">message</span>
              <span className="dim" style={{ fontSize: '0.82rem' }}>
                {words} words · edit freely before sending
              </span>
            </div>
            <div className="row gap-8">
              <Button size="sm" onClick={copy} disabled={!text}>
                {copied ? 'Copied ✓' : 'Copy to clipboard'}
              </Button>
            </div>
          </div>
          <div className="panel__body stack gap-14">
            {genError && <ErrorNote error={genError} onRetry={generate} />}

            {meta?.generated_by === 'template' && (
              <div className="notice notice--info">
                <div className="stack gap-4">
                  <span className="engraved">written locally</span>
                  <span style={{ fontSize: '0.86rem' }}>
                    {meta.fallback_reason || 'No LLM key configured'} — this draft was assembled
                    from your profile and the match explanation. Add <code>LLM_API_KEY</code> to
                    your <code>.env</code> and restart the backend for AI-written drafts.
                  </span>
                </div>
              </div>
            )}

            <textarea
              id="proposal-editor"
              className="field proposal"
              value={text}
              onChange={(e) => setText(e.target.value)}
              placeholder="Generate a draft, or write your message here."
              spellCheck="true"
            />

            {meta?.model && (
              <span className="engraved">
                model {meta.model}
              </span>
            )}
          </div>
        </Panel>

        <div className="stack gap-20">
          <Panel>
            <PanelHead title="tone" />
            <div className="panel__body stack gap-8">
              {TONES.map((t) => (
                <Button
                  key={t.key}
                  className="btn--block"
                  active={tone === t.key}
                  onClick={() => setTone(t.key)}
                >
                  {t.label}
                </Button>
              ))}
            </div>
          </Panel>

          <Panel>
            <PanelHead title="extra instructions" hint="Optional steer for this draft" />
            <div className="panel__body">
              <textarea
                className="field"
                style={{ minHeight: 110 }}
                value={instructions}
                onChange={(e) => setInstructions(e.target.value)}
                placeholder="e.g. Mention I can start immediately and work EU hours."
              />
            </div>
          </Panel>

          <Panel>
            <PanelHead title="before you send" />
            <div className="panel__body stack gap-8 muted" style={{ fontSize: '0.85rem' }}>
              <span>Check every claim against your real experience.</span>
              <span>Swap in the hiring manager's name if the posting gives one.</span>
              <span>Send it yourself — JobFndr never contacts anyone for you.</span>
            </div>
          </Panel>
        </div>
      </div>
    </>
  )
}
