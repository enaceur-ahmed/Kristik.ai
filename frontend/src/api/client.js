/**
 * API client — thin wrapper around fetch.
 * All requests go to /api (proxied to backend by Vite).
 */

const BASE = '/api'

async function request(method, path, body, isForm = false) {
  const opts = {
    method,
    headers: isForm ? {} : (body ? { 'Content-Type': 'application/json' } : {}),
    body: isForm ? body : (body ? JSON.stringify(body) : undefined),
  }

  const res = await fetch(`${BASE}${path}`, opts)

  if (!res.ok) {
    let detail = `HTTP ${res.status}`
    try {
      const err = await res.json()
      detail = err.detail || detail
    } catch {}
    throw new Error(detail)
  }

  if (res.status === 204) return null
  return res.json()
}

const get  = (path)         => request('GET',    path)
const post = (path, body)   => request('POST',   path, body)
const patch = (path, body)  => request('PATCH',  path, body)
const del  = (path)         => request('DELETE', path)

// ---------- Datasets ----------
export const api = {
  health:            ()         => get('/health'),
  dashboard:         ()         => get('/datasets/dashboard'),

  listDatasets:      ()         => get('/datasets'),
  getDataset:        (id)       => get(`/datasets/${id}`),
  deleteDataset:     (id)       => del(`/datasets/${id}`),

  uploadDataset: (file) => {
    const fd = new FormData()
    fd.append('file', file)
    return request('POST', '/datasets/upload', fd, true)
  },

  // Analysis workflow
  runProfile:        (id)       => post(`/datasets/${id}/profile`),
  getProfile:        (id)       => get(`/datasets/${id}/profile`),

  runQuality:        (id)       => post(`/datasets/${id}/quality`),
  getQuality:        (id)       => get(`/datasets/${id}/quality`),

  generateRecs:      (id)       => post(`/datasets/${id}/recommendations`),
  getRecs:           (id)       => get(`/datasets/${id}/recommendations`),
  updateRec:         (id, rid, action) => patch(`/datasets/${id}/recommendations/${rid}`, { action }),

  generatePipeline:  (id)       => post(`/datasets/${id}/pipeline/generate`),
  executePipeline:   (id, pid)  => post(`/datasets/${id}/pipeline/${pid}/execute`),
  getPipelines:      (id)       => get(`/datasets/${id}/pipeline`),

  getValidation:     (id)       => get(`/datasets/${id}/validation`),
  getAnalytics:      (id)       => get(`/datasets/${id}/analytics`),
  getLogs:           (id)       => get(`/datasets/${id}/logs`),
  getReport:         (id)       => get(`/datasets/${id}/report`),
  getPreview:        (id, limit) => get(`/datasets/${id}/preview${limit ? `?limit=${limit}` : ''}`),

  runBenchmark:      (id)       => post(`/benchmark/${id}`),

  // Discussion (chat)
  listConversations:    ()                => get('/conversations'),
  createConversation:   (body)            => post('/conversations', body),
  getConversation:      (id)              => get(`/conversations/${id}`),
  updateConversation:   (id, body)        => patch(`/conversations/${id}`, body),
  deleteConversation:   (id)              => del(`/conversations/${id}`),
  sendMessage:          (id, body)        => post(`/conversations/${id}/messages`, body),
}
