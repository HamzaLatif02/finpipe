import { useState, useRef, useCallback } from 'react'
import { io } from 'socket.io-client'

const SOCKET_URL = import.meta.env.DEV
  ? 'http://localhost:5001'
  : window.location.origin

// Fallback timed messages — plain ASCII dots, no unicode ellipsis
const PIPELINE_FALLBACK_STEPS = [
  'Connecting to Yahoo Finance...',
  'Fetching price history...',
  'Cleaning and validating data...',
  'Running financial analysis...',
  'Generating charts...',
  'Building PDF report...',
  'Almost done...',
]

const COMPARISON_FALLBACK_STEPS = [
  'Initialising comparison...',
  'Fetching data for first asset...',
  'Fetching data for second asset...',
  'Aligning price histories...',
  'Computing correlation and metrics...',
  'Generating comparison charts...',
  'Building combined PDF...',
]

function makeSocket() {
  return io(SOCKET_URL, {
    transports:    ['websocket', 'polling'],
    timeout:       10000,
    reconnection:  false,
    pingTimeout:   120000,   // 2 min — outlasts AI analysis calls
    pingInterval:  25000,    // heartbeat every 25 s keeps Render proxy alive
  })
}

function connectSocket() {
  return new Promise((resolve, reject) => {
    const socket = makeSocket()
    const timer  = setTimeout(() => {
      socket.disconnect()
      reject(new Error('WebSocket connection timed out'))
    }, 10000)
    socket.on('connect', () => { clearTimeout(timer); resolve(socket) })
    socket.on('connect_error', (err) => { clearTimeout(timer); socket.disconnect(); reject(err) })
  })
}

export function usePipelineSocket() {
  const [progress,      setProgress]      = useState({ percent: 0, message: '' })
  const [isLoading,     setIsLoading]     = useState(false)
  const [result,        setResult]        = useState(null)
  const [error,         setError]         = useState(null)
  const [usingFallback, setUsingFallback] = useState(false)

  // Refs that survive across closures and renders
  const socketRef      = useRef(null)
  const fallbackRef    = useRef(null)
  const runIdRef       = useRef(null)   // current run UUID — read in event handlers
  const isLoadingRef   = useRef(false)  // mirrors isLoading — safe to read in disconnect handler
  const pendingRunRef  = useRef(null)   // { type: 'pipeline'|'comparison', config, config_a, config_b }

  // ── Fallback helpers ─────────────────────────────────────────────────────

  function stopFallback() {
    if (fallbackRef.current) { clearInterval(fallbackRef.current); fallbackRef.current = null }
  }

  function startFallback(steps) {
    setProgress({ percent: 5, message: steps[0] })
    let idx = 1
    const total = steps.length
    fallbackRef.current = setInterval(() => {
      if (idx < total) {
        setProgress({ percent: Math.round(5 + (idx / total) * 80), message: steps[idx] })
        idx++
      }
    }, 4000)
  }

  // ── HTTP fallback runners ─────────────────────────────────────────────────

  async function httpPipeline(config) {
    setUsingFallback(true)
    startFallback(PIPELINE_FALLBACK_STEPS)
    try {
      const res  = await fetch('/api/pipeline/run', {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(config),
      })
      const data = await res.json()
      stopFallback()
      if (!res.ok || data.error) throw new Error(data.error || `HTTP ${res.status}`)
      setProgress({ percent: 100, message: 'Complete' })
      isLoadingRef.current = false
      setIsLoading(false)
      setResult(data)
      return data
    } catch (err) {
      stopFallback()
      isLoadingRef.current = false
      setIsLoading(false)
      setError(err.message)
      return null
    }
  }

  async function httpComparison(config_a, config_b) {
    setUsingFallback(true)
    startFallback(COMPARISON_FALLBACK_STEPS)
    try {
      const res  = await fetch('/api/comparison/run', {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ config_a, config_b }),
      })
      const data = await res.json()
      stopFallback()
      if (!res.ok || data.error) throw new Error(data.error || `HTTP ${res.status}`)
      setProgress({ percent: 100, message: 'Complete' })
      isLoadingRef.current = false
      setIsLoading(false)
      setResult(data)
      return data
    } catch (err) {
      stopFallback()
      isLoadingRef.current = false
      setIsLoading(false)
      setError(err.message)
      return null
    }
  }

  // ── Socket cleanup ────────────────────────────────────────────────────────

  function cleanupSocket(socket) {
    stopFallback()
    if (socket) {
      socket.off('joined')
      socket.off('pipeline_progress')
      socket.off('pipeline_complete')
      socket.off('pipeline_error')
      socket.off('comparison_complete')
      socket.off('disconnect')
      socket.off('ws_ping')
      socket.disconnect()
    }
    socketRef.current = null
    runIdRef.current  = null
  }

  // ── Disconnect handler — shared by pipeline and comparison ────────────────

  function makeDisconnectHandler(socket, resolve) {
    return (reason) => {
      console.warn('[WS] Disconnected:', reason)
      if (!isLoadingRef.current) return   // already resolved, nothing to do
      cleanupSocket(socket)
      const run = pendingRunRef.current
      if (!run) { setIsLoading(false); setError('WebSocket disconnected.'); resolve(null); return }
      // Switch to HTTP fallback transparently
      console.warn('[WS] Switching to HTTP fallback after disconnect')
      if (run.type === 'pipeline') {
        httpPipeline(run.config).then(resolve)
      } else {
        httpComparison(run.config_a, run.config_b).then(resolve)
      }
    }
  }

  // ── runPipeline ───────────────────────────────────────────────────────────

  const runPipeline = useCallback(async (config) => {
    setIsLoading(true); isLoadingRef.current = true
    setError(null); setResult(null)
    setProgress({ percent: 0, message: '' })
    setUsingFallback(false)

    const runId = crypto.randomUUID()
    runIdRef.current    = runId
    pendingRunRef.current = { type: 'pipeline', config }

    let socket = null
    try { socket = await connectSocket(); socketRef.current = socket }
    catch (_) { /* fall through to HTTP */ }

    if (socket) {
      return new Promise((resolve) => {
        // Register handlers with .off() first to prevent duplicates
        socket.off('joined')
        socket.on('joined', () => {
          socket.emit('start_pipeline', { run_id: runId, config })
        })

        socket.off('pipeline_progress')
        socket.on('pipeline_progress', (data) => {
          if (data.run_id !== runIdRef.current) return
          setProgress({ percent: data.percent, message: data.message })
        })

        socket.off('ws_ping')
        socket.on('ws_ping', () => { /* keepalive — no UI action */ })

        socket.off('pipeline_complete')
        socket.on('pipeline_complete', (data) => {
          if (data.run_id !== runIdRef.current) return
          cleanupSocket(socket)
          isLoadingRef.current = false
          setIsLoading(false)
          setResult(data)
          resolve(data)
        })

        socket.off('pipeline_error')
        socket.on('pipeline_error', (data) => {
          if (data.run_id !== runIdRef.current) return
          cleanupSocket(socket)
          isLoadingRef.current = false
          setIsLoading(false)
          setError(data.error || 'Pipeline failed')
          resolve(null)
        })

        socket.off('disconnect')
        socket.on('disconnect', makeDisconnectHandler(socket, resolve))

        socket.emit('join', { run_id: runId })
      })
    }

    // No WebSocket — go straight to HTTP
    return httpPipeline(config)
  }, [])

  // ── runComparison ─────────────────────────────────────────────────────────

  const runComparison = useCallback(async (config_a, config_b) => {
    setIsLoading(true); isLoadingRef.current = true
    setError(null); setResult(null)
    setProgress({ percent: 0, message: '' })
    setUsingFallback(false)

    const runId = crypto.randomUUID()
    runIdRef.current      = runId
    pendingRunRef.current = { type: 'comparison', config_a, config_b }

    let socket = null
    try { socket = await connectSocket(); socketRef.current = socket }
    catch (_) { /* fall through to HTTP */ }

    if (socket) {
      return new Promise((resolve) => {
        socket.off('joined')
        socket.on('joined', () => {
          socket.emit('start_comparison', { run_id: runId, config_a, config_b })
        })

        socket.off('pipeline_progress')
        socket.on('pipeline_progress', (data) => {
          if (data.run_id !== runIdRef.current) return
          setProgress({ percent: data.percent, message: data.message })
        })

        socket.off('ws_ping')
        socket.on('ws_ping', () => { /* keepalive — no UI action */ })

        socket.off('comparison_complete')
        socket.on('comparison_complete', (data) => {
          if (data.run_id !== runIdRef.current) return
          cleanupSocket(socket)
          isLoadingRef.current = false
          setIsLoading(false)
          setResult(data)
          resolve(data)
        })

        socket.off('pipeline_error')
        socket.on('pipeline_error', (data) => {
          if (data.run_id !== runIdRef.current) return
          cleanupSocket(socket)
          isLoadingRef.current = false
          setIsLoading(false)
          setError(data.error || 'Comparison failed')
          resolve(null)
        })

        socket.off('disconnect')
        socket.on('disconnect', makeDisconnectHandler(socket, resolve))

        socket.emit('join', { run_id: runId })
      })
    }

    return httpComparison(config_a, config_b)
  }, [])

  // ── resetResult ───────────────────────────────────────────────────────────

  const resetResult = useCallback(() => {
    setResult(null); setError(null)
    setProgress({ percent: 0, message: '' })
    setUsingFallback(false)
    pendingRunRef.current = null
  }, [])

  return { progress, isLoading, result, error, usingFallback, runPipeline, runComparison, resetResult }
}
