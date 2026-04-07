import { useState, useRef, useCallback } from 'react'
import { io } from 'socket.io-client'

const SOCKET_URL = import.meta.env.DEV
  ? 'http://localhost:5001'
  : window.location.origin

const CONNECT_TIMEOUT_MS = 5000

// Fallback timed messages for when WebSocket is unavailable
const PIPELINE_FALLBACK_STEPS = [
  'Connecting to Yahoo Finance…',
  'Fetching price history…',
  'Cleaning and validating data…',
  'Running financial analysis…',
  'Generating charts…',
  'Building PDF report…',
  'Almost done…',
]

const COMPARISON_FALLBACK_STEPS = [
  'Initialising comparison…',
  'Fetching data for first asset…',
  'Fetching data for second asset…',
  'Aligning price histories…',
  'Computing correlation and metrics…',
  'Generating comparison charts…',
  'Building combined PDF…',
]

function connect() {
  return new Promise((resolve, reject) => {
    const socket = io(SOCKET_URL, {
      transports: ['websocket', 'polling'],
      timeout: CONNECT_TIMEOUT_MS,
    })
    const timer = setTimeout(() => {
      socket.disconnect()
      reject(new Error('WebSocket connection timed out'))
    }, CONNECT_TIMEOUT_MS)
    socket.on('connect', () => {
      clearTimeout(timer)
      resolve(socket)
    })
    socket.on('connect_error', (err) => {
      clearTimeout(timer)
      socket.disconnect()
      reject(err)
    })
  })
}

export function usePipelineSocket() {
  const [progress,      setProgress]      = useState({ percent: 0, message: '' })
  const [isLoading,     setIsLoading]     = useState(false)
  const [result,        setResult]        = useState(null)
  const [error,         setError]         = useState(null)
  const [usingFallback, setUsingFallback] = useState(false)

  const socketRef   = useRef(null)
  const fallbackRef = useRef(null)

  function stopFallback() {
    if (fallbackRef.current) {
      clearInterval(fallbackRef.current)
      fallbackRef.current = null
    }
  }

  function startFallback(steps) {
    setProgress({ percent: 5, message: steps[0] })
    let idx = 1
    const total = steps.length
    fallbackRef.current = setInterval(() => {
      if (idx < total) {
        const percent = Math.round(5 + (idx / total) * 80)
        setProgress({ percent, message: steps[idx] })
        idx++
      }
    }, 4000)
  }

  function cleanup(socket) {
    stopFallback()
    if (socket) socket.disconnect()
    socketRef.current = null
  }

  const runPipeline = useCallback(async (config) => {
    setIsLoading(true)
    setError(null)
    setResult(null)
    setProgress({ percent: 0, message: '' })
    setUsingFallback(false)

    const runId = crypto.randomUUID()

    // ── Try WebSocket path ────────────────────────────────────────────────
    let socket = null
    try {
      socket = await connect()
      socketRef.current = socket
    } catch (_) {
      // Fall back to HTTP
    }

    if (socket) {
      return new Promise((resolve) => {
        socket.emit('join', { run_id: runId })

        socket.on('joined', () => {
          socket.emit('start_pipeline', { run_id: runId, config })
        })

        socket.on('pipeline_progress', (data) => {
          if (data.run_id !== runId) return
          setProgress({ percent: data.percent, message: data.message })
        })

        socket.on('pipeline_complete', (data) => {
          if (data.run_id !== runId) return
          cleanup(socket)
          setIsLoading(false)
          setResult(data)
          resolve(data)
        })

        socket.on('pipeline_error', (data) => {
          if (data.run_id !== runId) return
          cleanup(socket)
          setIsLoading(false)
          setError(data.error || 'Pipeline failed')
          resolve(null)
        })

        socket.on('disconnect', () => {
          cleanup(socket)
          setIsLoading(false)
          setError('WebSocket disconnected unexpectedly')
          resolve(null)
        })
      })
    }

    // ── HTTP fallback ─────────────────────────────────────────────────────
    setUsingFallback(true)
    startFallback(PIPELINE_FALLBACK_STEPS)
    try {
      const res = await fetch('/api/pipeline/run', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(config),
      })
      const data = await res.json()
      stopFallback()
      if (!res.ok || data.error) throw new Error(data.error || `HTTP ${res.status}`)
      setProgress({ percent: 100, message: 'Complete' })
      setIsLoading(false)
      setResult(data)
      return data
    } catch (err) {
      stopFallback()
      setIsLoading(false)
      setError(err.message)
      return null
    }
  }, [])

  const runComparison = useCallback(async (config_a, config_b) => {
    setIsLoading(true)
    setError(null)
    setResult(null)
    setProgress({ percent: 0, message: '' })
    setUsingFallback(false)

    const runId = crypto.randomUUID()

    // ── Try WebSocket path ────────────────────────────────────────────────
    let socket = null
    try {
      socket = await connect()
      socketRef.current = socket
    } catch (_) {
      // Fall back to HTTP
    }

    if (socket) {
      return new Promise((resolve) => {
        socket.emit('join', { run_id: runId })

        socket.on('joined', () => {
          socket.emit('start_comparison', { run_id: runId, config_a, config_b })
        })

        socket.on('pipeline_progress', (data) => {
          if (data.run_id !== runId) return
          setProgress({ percent: data.percent, message: data.message })
        })

        socket.on('comparison_complete', (data) => {
          if (data.run_id !== runId) return
          cleanup(socket)
          setIsLoading(false)
          setResult(data)
          resolve(data)
        })

        socket.on('pipeline_error', (data) => {
          if (data.run_id !== runId) return
          cleanup(socket)
          setIsLoading(false)
          setError(data.error || 'Comparison failed')
          resolve(null)
        })

        socket.on('disconnect', () => {
          cleanup(socket)
          setIsLoading(false)
          setError('WebSocket disconnected unexpectedly')
          resolve(null)
        })
      })
    }

    // ── HTTP fallback ─────────────────────────────────────────────────────
    setUsingFallback(true)
    startFallback(COMPARISON_FALLBACK_STEPS)
    try {
      const res = await fetch('/api/comparison/run', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ config_a, config_b }),
      })
      const data = await res.json()
      stopFallback()
      if (!res.ok || data.error) throw new Error(data.error || `HTTP ${res.status}`)
      setProgress({ percent: 100, message: 'Complete' })
      setIsLoading(false)
      setResult(data)
      return data
    } catch (err) {
      stopFallback()
      setIsLoading(false)
      setError(err.message)
      return null
    }
  }, [])

  const resetResult = useCallback(() => {
    setResult(null)
    setError(null)
    setProgress({ percent: 0, message: '' })
    setUsingFallback(false)
  }, [])

  return {
    progress,
    isLoading,
    result,
    error,
    usingFallback,
    runPipeline,
    runComparison,
    resetResult,
  }
}
