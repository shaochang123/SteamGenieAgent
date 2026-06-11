import Vue from 'vue'

export function createEmptyOverview() {
  return {
    configured: false,
    message: '配置 Steam API Key 和 SteamID64 后可查看个人概览。',
    profile: null,
    stats: null,
    recentGames: [],
  }
}

export function createEmptyDeals() {
  return {
    configured: false,
    message: '配置 Steam 信息后可同时查看个人概览和商店卡片。',
    items: [],
  }
}

export const appStore = Vue.observable({
  profiles: [],
  selectedProfileId: '',
  selectedProfile: null,
  messages: [],
  streamingContent: '',
  steamOverview: createEmptyOverview(),
  steamDeals: createEmptyDeals(),
  dialogs: {
    createProfile: false,
    settings: false,
  },
  loading: {
    profiles: false,
    conversation: false,
    sending: false,
    steam: false,
    createProfile: false,
    saveSettings: false,
  },
  error: {
    profiles: '',
    chat: '',
    steam: '',
    createProfile: '',
    settings: '',
  },
})
