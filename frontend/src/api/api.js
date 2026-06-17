import axios from 'axios'

const OLLAMA_PORTS = new Set(['11343', '11434'])
const FASTAPI_PORT = '8000'
const LOOPBACK_HOSTS = new Set(['localhost', '127.0.0.1', '::1'])

function inferredApiBaseUrl() {
  if (typeof window === 'undefined' || !window.location?.hostname) {
    return 'http://127.0.0.1:8000'
  }

  return `${window.location.protocol}//${window.location.hostname}:${FASTAPI_PORT}`
}

function isOllamaUrl(value) {
  try {
    const url = new URL(value)
    return OLLAMA_PORTS.has(url.port) || url.pathname.includes('/api/chat')
  } catch {
    return value.includes(':11343') || value.includes(':11434') || value.includes('/api/chat')
  }
}

function isLoopbackApiUrl(value) {
  try {
    return LOOPBACK_HOSTS.has(new URL(value).hostname)
  } catch {
    return false
  }
}

function isPageLoadedFromLanHost() {
  return typeof window !== 'undefined' &&
    window.location?.hostname &&
    !LOOPBACK_HOSTS.has(window.location.hostname)
}

function apiBaseUrl() {
  const fallback = inferredApiBaseUrl()
  const configured = (process.env.VUE_APP_API_BASE_URL || fallback).replace(/\/+$/, '')
  if (!isOllamaUrl(configured)) {
    if (isPageLoadedFromLanHost() && isLoopbackApiUrl(configured)) {
      console.warn(
        `VUE_APP_API_BASE_URL points to local loopback (${configured}); falling back to FastAPI ${fallback}.`
      )
      return fallback
    }
    return configured
  }

  console.warn(
    `VUE_APP_API_BASE_URL points to Ollama (${configured}); falling back to FastAPI ${fallback}.`
  )
  return fallback
}

const API_BASE_URL = apiBaseUrl()

const api = axios.create({
  baseURL: API_BASE_URL,
  timeout: 60000,
})

export function normalizeError(error) {
  if (error?.message === 'Network Error') {
    return `无法连接后端服务：${API_BASE_URL}`
  }

  return (
    error?.response?.data?.detail ||
    error?.response?.data?.message ||
    error?.message ||
    '请求失败'
  )
}

export function listProfiles() {
  return api.get('/profiles')
}

export function createProfile(displayName) {
  return api.post('/profiles', { displayName })
}

export function getProfile(profileId) {
  return api.get(`/profiles/${profileId}`)
}

export function deleteProfile(profileId) {
  return api.delete(`/profiles/${profileId}`)
}

export function updateProfileConfig(profileId, payload) {
  return api.patch(`/profiles/${profileId}/config`, payload)
}

export function getProfileMessages(profileId) {
  return api.get(`/profiles/${profileId}/messages`)
}

export function getSteamOverview(profileId) {
  return api.get(`/profiles/${profileId}/steam/overview`)
}

export function getSteamDeals(profileId) {
  return api.get(`/profiles/${profileId}/steam/deals`)
}

export function getKnowledge(profileId) {
  return api.get(`/profiles/${profileId}/knowledge`)
}

export function uploadKnowledge(profileId, file) {
  const formData = new FormData()
  formData.append('file', file)
  return api.post(`/profiles/${profileId}/knowledge`, formData, {
    headers: { 'Content-Type': 'multipart/form-data' },
  })
}

export function deleteKnowledge(profileId, filename) {
  return api.delete(`/profiles/${profileId}/knowledge/${encodeURIComponent(filename)}`)
}

// Axios does not expose browser ReadableStream chunks consistently, so the
// streaming chat endpoint uses fetch and dispatches parsed SSE events manually.
export async function sendChatStream(profileId, question, k, callbacks) {
  const { onToken, onDone, onError, onToolStart, onToolResult } = callbacks

  try {
    const response = await fetch(`${API_BASE_URL}/chat/stream`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ profileId, question, k }),
    })

    if (!response.ok) {
      const errorText = await response.text()
      let detail = errorText
      try {
        const parsed = JSON.parse(errorText)
        detail = parsed.detail || errorText
      } catch {
        // use raw text
      }
      onError?.(detail)
      return
    }

    const reader = response.body.getReader()
    const decoder = new TextDecoder()
    let buffer = ''

    let chunk = await reader.read()
    while (!chunk.done) {
      buffer += decoder.decode(chunk.value, { stream: true })

      // Network chunks can split in the middle of an SSE line. Keep the final
      // partial line in buffer until the next chunk arrives.
      const lines = buffer.split('\n')
      buffer = lines.pop() || ''

      for (const line of lines) {
        if (!line.startsWith('data: ')) continue
        const dataStr = line.slice(6)
        try {
          const event = JSON.parse(dataStr)
          switch (event.type) {
            case 'token': onToken?.(event.content); break
            case 'done': onDone?.(event.content); break
            case 'error': onError?.(event.content); break
            case 'tool_start': onToolStart?.(event.tool); break
            case 'tool_result': onToolResult?.(event.tool, event.result); break
          }
        } catch {
          // skip malformed event
        }
      }
      chunk = await reader.read()
    }
  } catch (error) {
    onError?.(error.message || '网络请求失败')
  }
}
