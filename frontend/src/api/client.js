import axios from 'axios'

const http = axios.create({ baseURL: '/api' })

function unwrap(response) {
  const data = response.data
  if (data?.error) throw new Error(data.error)
  return data
}

// ── Schedule token store (localStorage) ──────────────────────────────────────
// Persists a map of { job_id: token } so the client can authenticate its
// own scheduled jobs across page reloads.

const TOKEN_KEY = 'fp_schedule_tokens'

function loadTokens() {
  try {
    return JSON.parse(localStorage.getItem(TOKEN_KEY) || '{}')
  } catch {
    return {}
  }
}

function saveTokens(tokens) {
  localStorage.setItem(TOKEN_KEY, JSON.stringify(tokens))
}

function storeJobToken(jobId, token) {
  const tokens = loadTokens()
  tokens[jobId] = token
  saveTokens(tokens)
}

function dropJobToken(jobId) {
  const tokens = loadTokens()
  delete tokens[jobId]
  saveTokens(tokens)
}

function allTokensHeader() {
  const tokens = Object.values(loadTokens())
  return tokens.length ? tokens.join(',') : ''
}

function tokenForJob(jobId) {
  return loadTokens()[jobId] || ''
}

// ── API functions ─────────────────────────────────────────────────────────────

export async function getCategories() {
  const res = await http.get('/assets/categories')
  return unwrap(res).categories
}

export async function getPeriods() {
  const res = await http.get('/assets/periods')
  return unwrap(res).periods
}

export async function getIntervals() {
  const res = await http.get('/assets/intervals')
  return unwrap(res).intervals
}

export async function validateTicker(symbol) {
  const res = await http.get('/assets/validate', { params: { symbol } })
  return unwrap(res)
}

export async function runPipeline(config) {
  const res = await http.post('/pipeline/run', config)
  const data = res.data
  if (data?.status === 'error') {
    const msg = data.stage ? `[${data.stage}] ${data.error}` : data.error
    throw new Error(msg)
  }
  return data
}

export async function getPreviousRuns() {
  const res = await http.get('/pipeline/status')
  return unwrap(res).assets
}

export function getChartUrl(filename) {
  return `/api/reports/charts/${filename}`
}

export function getPdfUrl(symbol) {
  return `/api/reports/pdf/${symbol}`
}

export async function listReports(symbol) {
  const res = await http.get(`/reports/list/${symbol}`)
  return unwrap(res)
}

export async function addSchedule(payload) {
  const res = await http.post('/schedule/add', payload)
  const data = unwrap(res)
  if (data.job_id && data.token) {
    storeJobToken(data.job_id, data.token)
  }
  return data
}

export async function removeSchedule(jobId) {
  const res = await http.delete(`/schedule/remove/${jobId}`, {
    headers: { 'X-Schedule-Token': tokenForJob(jobId) },
  })
  const data = unwrap(res)
  dropJobToken(jobId)
  return data
}

export async function listSchedules() {
  const header = allTokensHeader()
  if (!header) return []
  const res = await http.get('/schedule/list', {
    headers: { 'X-Schedule-Token': header },
  })
  return unwrap(res).jobs
}
