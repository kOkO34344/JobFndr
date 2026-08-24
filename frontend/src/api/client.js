/**
 * Thin client for the JobFndr API.
 *
 * In Docker the SPA is served by nginx which proxies /api to the backend
 * service, so the default base is a same-origin relative path.
 */
const BASE = import.meta.env.VITE_API_BASE || '/api'

export class ApiError extends Error {
  constructor(message, status, detail) {
    super(message)
    this.name = 'ApiError'
    this.status = status
    this.detail = detail
  }
}

async function request(path, { method = 'GET', body, signal, timeout } = {}) {
  const controller = new AbortController()
  const timer = timeout ? setTimeout(() => controller.abort(), timeout) : null
  if (signal) signal.addEventListener('abort', () => controller.abort())

  const options = { method, signal: controller.signal, headers: {} }
  if (body instanceof FormData) {
    options.body = body
  } else if (body !== undefined) {
    options.headers['Content-Type'] = 'application/json'
    options.body = JSON.stringify(body)
  }

  let response
  try {
    response = await fetch(`${BASE}${path}`, options)
  } catch (err) {
    if (err.name === 'AbortError') throw new ApiError('Request timed out', 0)
    throw new ApiError('Cannot reach the backend. Is it running?', 0)
  } finally {
    if (timer) clearTimeout(timer)
  }

  if (response.status === 204) return null

  const text = await response.text()
  const payload = text ? safeJson(text) : null

  if (!response.ok) {
    const detail = payload?.detail
    const message =
      typeof detail === 'string'
        ? detail
        : Array.isArray(detail)
          ? detail.map((d) => d.msg).join('; ')
          : `Request failed (${response.status})`
    throw new ApiError(message, response.status, detail)
  }
  return payload
}

function safeJson(text) {
  try {
    return JSON.parse(text)
  } catch {
    return null
  }
}

/** Build a query string, repeating keys for array values. */
function qs(params = {}) {
  const search = new URLSearchParams()
  for (const [key, value] of Object.entries(params)) {
    if (value === undefined || value === null || value === '') continue
    if (Array.isArray(value)) value.forEach((v) => search.append(key, v))
    else search.append(key, value)
  }
  const str = search.toString()
  return str ? `?${str}` : ''
}

export const api = {
  health: () => request('/health'),

  getProfile: () => request('/profile'),
  updateProfile: (payload) => request('/profile', { method: 'PUT', body: payload }),
  uploadCv: (file) => {
    const form = new FormData()
    form.append('file', file)
    return request('/profile/cv', { method: 'POST', body: form, timeout: 120000 })
  },

  listJobs: (filters) => request(`/jobs${qs(filters)}`),
  getJob: (id) => request(`/jobs/${id}`),
  categories: () => request('/jobs/categories'),
  // A scan hits every source then embeds, so it needs a long ceiling.
  scan: (sources) => request('/jobs/scan', { method: 'POST', body: { sources }, timeout: 600000 }),
  rerank: () => request('/jobs/rerank', { method: 'POST' }),
  labelJob: (id, status, notes) =>
    request(`/jobs/${id}/label`, { method: 'POST', body: { status, notes } }),
  clearLabel: (id) => request(`/jobs/${id}/label`, { method: 'DELETE' }),

  createProposal: (id, payload) =>
    request(`/jobs/${id}/proposal`, { method: 'POST', body: payload, timeout: 180000 }),
  latestProposal: (id) => request(`/jobs/${id}/proposal`),
  proposalHistory: (id) => request(`/jobs/${id}/proposals`),
  llmStatus: () => request('/llm/status'),

  listSources: () => request('/sources'),
  toggleSource: (name, enabled) =>
    request(`/sources/${name}`, { method: 'PUT', body: { enabled } }),
  attributions: () => request('/sources/attributions'),

  analytics: () => request('/analytics'),
}
