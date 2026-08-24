import { useCallback, useEffect, useRef, useState } from 'react'

/**
 * Run an API call and track its lifecycle.
 *
 * `deps` behaves like a useEffect dependency list. Results from a superseded
 * call are discarded so a slow earlier request cannot overwrite a newer one.
 */
export function useApi(fn, deps = [], { immediate = true } = {}) {
  const [data, setData] = useState(null)
  const [error, setError] = useState(null)
  const [loading, setLoading] = useState(immediate)
  const callId = useRef(0)
  const mounted = useRef(true)

  useEffect(() => {
    mounted.current = true
    return () => {
      mounted.current = false
    }
  }, [])

  const run = useCallback(async (...args) => {
    const id = ++callId.current
    setLoading(true)
    setError(null)
    try {
      const result = await fn(...args)
      if (mounted.current && id === callId.current) setData(result)
      return result
    } catch (err) {
      if (mounted.current && id === callId.current) setError(err)
      throw err
    } finally {
      if (mounted.current && id === callId.current) setLoading(false)
    }
    // fn is intentionally excluded: callers pass inline closures.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, deps)

  useEffect(() => {
    if (!immediate) return
    run().catch(() => {})
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [run, immediate])

  return { data, error, loading, run, setData }
}

/** Persist a piece of UI state (filters, tone) across reloads. */
export function useStoredState(key, initial) {
  const [value, setValue] = useState(() => {
    try {
      const raw = localStorage.getItem(key)
      return raw ? JSON.parse(raw) : initial
    } catch {
      return initial
    }
  })

  useEffect(() => {
    try {
      localStorage.setItem(key, JSON.stringify(value))
    } catch {
      /* private mode or blocked storage: fall back to in-memory only */
    }
  }, [key, value])

  return [value, setValue]
}
