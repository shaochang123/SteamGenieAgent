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

export function sendChat(profileId, question, k = 3) {
  return api.post('/chat', {
    profileId,
    question,
    k,
  })
}

export function getSteamOverview(profileId) {
  return api.get(`/profiles/${profileId}/steam/overview`)
}

export function getSteamDeals(profileId) {
  return api.get(`/profiles/${profileId}/steam/deals`)
}
