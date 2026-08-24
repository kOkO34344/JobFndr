import { NavLink } from 'react-router-dom'

const LINKS = [
  { to: '/', label: 'Jobs', hint: 'Ranked deck', end: true },
  { to: '/analytics', label: 'Analytics', hint: 'Pipeline readout' },
  { to: '/profile', label: 'Profile', hint: 'CV & preferences' },
]

export default function NavRail({ llm }) {
  return (
    <nav className="rail" aria-label="Main">
      <div className="rail__brand">
        <div className="rail__mark" aria-hidden="true" />
        <div className="stack">
          <span className="rail__wordmark">JobFndr</span>
          <span className="engraved">single operator</span>
        </div>
      </div>

      <ul className="rail__links">
        {LINKS.map((link) => (
          <li key={link.to}>
            <NavLink
              to={link.to}
              end={link.end}
              className={({ isActive }) => `rail__link${isActive ? ' rail__link--on' : ''}`}
            >
              <span className="rail__linkLabel">{link.label}</span>
              <span className="engraved">{link.hint}</span>
            </NavLink>
          </li>
        ))}
      </ul>

      <div className="rail__foot">
        <span className="engraved">proposal engine</span>
        <span
          className={`status status--${llm?.configured ? 'shortlisted' : 'maybe'} mono`}
          style={{ fontSize: '0.72rem' }}
        >
          {llm?.configured ? llm.model : 'local drafts'}
        </span>
      </div>
    </nav>
  )
}
