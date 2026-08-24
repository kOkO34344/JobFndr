import { Route, Routes } from 'react-router-dom'

import NavRail from './components/NavRail.jsx'
import { api } from './api/client.js'
import { useApi } from './hooks/useApi.js'
import Analytics from './pages/Analytics.jsx'
import Dashboard from './pages/Dashboard.jsx'
import JobDetail from './pages/JobDetail.jsx'
import ProfileSettings from './pages/ProfileSettings.jsx'
import ProposalDraft from './pages/ProposalDraft.jsx'

export default function App() {
  const llm = useApi(() => api.llmStatus(), [])

  return (
    <div className="shell">
      <NavRail llm={llm.data} />
      <main className="main">
        <div className="main__inner rise">
          <Routes>
            <Route path="/" element={<Dashboard />} />
            <Route path="/jobs/:id" element={<JobDetail />} />
            <Route path="/jobs/:id/proposal" element={<ProposalDraft />} />
            <Route path="/profile" element={<ProfileSettings />} />
            <Route path="/analytics" element={<Analytics />} />
            <Route path="*" element={<NotFound />} />
          </Routes>
        </div>
      </main>
    </div>
  )
}

function NotFound() {
  return (
    <div className="empty">
      <div className="empty__ring" aria-hidden="true" />
      <h3>No such screen</h3>
      <p className="muted">That route does not exist. Head back to the job deck.</p>
      <a className="btn btn--primary" href="/">
        Back to jobs
      </a>
    </div>
  )
}
