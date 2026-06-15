import { getSteamDeals, getSteamOverview, normalizeError } from '../api/api'
import { createEmptyDeals, createEmptyOverview } from '../store/appStore'

export function resetSteamCards(state) {
  state.steamOverview = createEmptyOverview()
  state.steamDeals = createEmptyDeals()
}

export async function loadSteamCards(profileId) {
  const [overviewRes, dealsRes] = await Promise.allSettled([
    getSteamOverview(profileId),
    getSteamDeals(profileId),
  ])

  const result = {
    overview: createEmptyOverview(),
    deals: createEmptyDeals(),
    error: '',
  }

  if (overviewRes.status === 'fulfilled') {
    result.overview = overviewRes.value.data || result.overview
  } else {
    result.error = normalizeError(overviewRes.reason)
  }

  if (dealsRes.status === 'fulfilled') {
    result.deals = dealsRes.value.data || result.deals
  } else {
    result.error = result.error || normalizeError(dealsRes.reason)
  }

  return result
}
