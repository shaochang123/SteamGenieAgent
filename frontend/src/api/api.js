import axios from 'axios'

const api = axios.create({
  baseURL: process.env.VUE_APP_API_BASE_URL || 'http://127.0.0.1:8000',
  timeout: 60000,
})

function unwrapError(error) {
  return (
    error?.response?.data?.detail ||
    error?.response?.data?.message ||
    error?.message ||
    '请求失败'
  )
}

export function normalizeError(error) {
  return unwrapError(error)
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
  const baseURL = process.env.VUE_APP_API_BASE_URL || 'http://127.0.0.1:8000'
  const { onToken, onDone, onError, onToolStart, onToolResult } = callbacks

  try {
    const response = await fetch(`${baseURL}/chat/stream`, {
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
      } catch (_) {
        // use raw text
      }
      if (onError) onError(detail)
      return
    }

    const reader = response.body.getReader()
    const decoder = new TextDecoder()
    let buffer = ''

    let reading = true
    while (reading) {
      const { done, value } = await reader.read()
      if (done) { reading = false; break }
      buffer += decoder.decode(value, { stream: true })

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
            case 'token':
              if (onToken) onToken(event.content)
              break
            case 'done':
              if (onDone) onDone(event.content)
              break
            case 'error':
              if (onError) onError(event.content)
              break
            case 'tool_start':
              if (onToolStart) onToolStart(event.tool)
              break
            case 'tool_result':
              if (onToolResult) onToolResult(event.tool, event.result)
              break
          }
        } catch (_) {
          // skip malformed event
        }
      }
    }
  } catch (error) {
    if (onError) onError(error.message || '网络请求失败')
  }
}
