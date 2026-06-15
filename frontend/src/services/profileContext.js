import { getProfile, getProfileMessages, normalizeError } from '../api/api'

export async function loadProfileContext(profileId) {
  const [profileRes, messagesRes] = await Promise.allSettled([
    getProfile(profileId),
    getProfileMessages(profileId),
  ])

  const context = {
    profile: null,
    messages: [],
    error: '',
  }

  if (profileRes.status === 'fulfilled') {
    context.profile = profileRes.value.data.profile
  } else {
    context.error = normalizeError(profileRes.reason)
  }

  if (messagesRes.status === 'fulfilled') {
    context.messages = messagesRes.value.data.messages || []
  } else {
    context.error = context.error || normalizeError(messagesRes.reason)
  }

  return context
}
