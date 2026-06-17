<template>
  <div id="app" :class="deviceClasses">
    <div class="background background--top"></div>
    <div class="background background--bottom"></div>

    <main class="shell">
      <section class="panel panel--sidebar">
        <ProfileSidebar
          :profiles="state.profiles"
          :selected-profile-id="state.selectedProfileId"
          @create-profile="state.dialogs.createProfile = true"
          @delete-profile="handleDeleteProfile"
          @select-profile="handleProfileSelect"
        />
      </section>

      <section class="panel panel--chat">
        <ChatPane
          :profile="state.selectedProfile"
          :messages="activeChatSession.messages"
          :loading="activeChatSession.loading"
          :sending="activeChatSession.sending"
          :error="activeChatSession.error"
          :streaming-content="activeChatSession.streamingContent"
          @open-settings="state.dialogs.settings = true"
          @send-message="handleSendMessage"
        />
      </section>

      <section v-if="!usesSteamDrawer" class="panel panel--steam">
        <div class="steam-stack">
          <SteamOverviewCard
            :overview="state.steamOverview"
            :loading="state.loading.steam"
            @refresh="refreshSteamData"
          />
          <SteamDealsCard :deals="state.steamDeals" :loading="state.loading.steam" />
        </div>
      </section>
    </main>

    <button
      v-if="usesSteamDrawer && !state.ui.steamDrawerOpen"
      class="steam-drawer-toggle"
      type="button"
      @click="openSteamDrawer"
    >
      <span>Steam</span>
      <strong>玩家状态</strong>
    </button>

    <div
      v-if="usesSteamDrawer && state.ui.steamDrawerOpen"
      class="steam-drawer-backdrop"
      @click="closeSteamDrawer"
    ></div>

    <aside
      v-if="usesSteamDrawer"
      class="steam-drawer"
      :class="{ 'steam-drawer--open': state.ui.steamDrawerOpen }"
      :aria-hidden="!state.ui.steamDrawerOpen"
    >
      <header class="steam-drawer__header">
        <div>
          <p class="eyebrow">Steam</p>
          <h2>玩家状态</h2>
        </div>
        <button class="steam-drawer__close" type="button" @click="closeSteamDrawer">
          关闭
        </button>
      </header>
      <div class="steam-stack">
        <SteamOverviewCard
          :overview="state.steamOverview"
          :loading="state.loading.steam"
          @refresh="refreshSteamData"
        />
        <SteamDealsCard :deals="state.steamDeals" :loading="state.loading.steam" />
      </div>
    </aside>

    <p v-for="error in floatingErrors" :key="error.key" :class="['floating-error', error.className]">
      {{ error.text }}
    </p>

    <CreateProfileDialog
      :visible="state.dialogs.createProfile"
      :loading="state.loading.createProfile"
      :error="state.error.createProfile"
      @close="closeCreateProfile"
      @submit="handleCreateProfile"
    />

    <SettingsSheet
      :visible="state.dialogs.settings"
      :profile="state.selectedProfile"
      :saving="state.loading.saveSettings"
      @close="closeSettings"
      @save="handleSaveSettings"
    />
  </div>
</template>

<script>
import {
  createProfile,
  deleteProfile,
  listProfiles,
  normalizeError,
  updateProfileConfig,
} from './api/api'
import ChatPane from './components/ChatPane.vue'
import CreateProfileDialog from './components/CreateProfileDialog.vue'
import ProfileSidebar from './components/ProfileSidebar.vue'
import SettingsSheet from './components/SettingsSheet.vue'
import SteamDealsCard from './components/SteamDealsCard.vue'
import SteamOverviewCard from './components/SteamOverviewCard.vue'
import { watchDeviceMode } from './services/deviceMode'
import { loadProfileContext } from './services/profileContext'
import { validateProfileSettings } from './services/settingsValidation'
import { loadSteamCards, resetSteamCards } from './services/steamCards'
import { appStore } from './store/appStore'
import {
  activeChatSession,
  deleteChatSession,
  ensureChatSession,
  sendProfileMessage,
} from './store/chatSessions'

export default {
  name: 'App',
  components: {
    ChatPane,
    CreateProfileDialog,
    ProfileSidebar,
    SettingsSheet,
    SteamDealsCard,
    SteamOverviewCard,
  },
  data() {
    return {
      state: appStore,
      stopDeviceWatcher: null,
    }
  },
  async created() {
    this.stopDeviceWatcher = watchDeviceMode((device) => {
      Object.assign(this.state.device, device)
      if (!['mobile', 'tablet'].includes(device.mode)) {
        this.state.ui.steamDrawerOpen = false
      }
    })
    await this.loadProfiles()
  },
  beforeDestroy() {
    this.stopDeviceWatcher?.()
  },
  computed: {
    activeChatSession() {
      return activeChatSession(this.state)
    },
    deviceClasses() {
      const device = this.state.device
      return [
        `device-${device.mode || 'desktop'}`,
        device.isTouch ? 'device-touch' : 'device-pointer',
      ]
    },
    isMobileDevice() {
      return this.state.device.mode === 'mobile'
    },
    usesSteamDrawer() {
      return this.state.device.mode === 'mobile' || this.state.device.mode === 'tablet'
    },
    floatingErrors() {
      return [
        { key: 'profiles', text: this.state.error.profiles, className: '' },
        { key: 'settings', text: this.state.error.settings, className: 'floating-error--bottom' },
        { key: 'steam', text: this.state.error.steam, className: 'floating-error--bottom-secondary' },
      ].filter((error) => error.text)
    },
  },
  methods: {
    openSteamDrawer() {
      this.state.ui.steamDrawerOpen = true
      this.state.ui.steamDrawerTouched = true
    },
    closeSteamDrawer() {
      this.state.ui.steamDrawerOpen = false
      this.state.ui.steamDrawerTouched = true
    },
    isSelectedProfile(profileId) {
      return this.state.selectedProfileId === profileId
    },
    async refreshProfileSummaries(preferredProfileId) {
      const response = await listProfiles()
      this.state.profiles = response.data.profiles || []

      if (
        preferredProfileId &&
        this.state.profiles.some((profile) => profile.id === preferredProfileId)
      ) {
        this.state.selectedProfileId = preferredProfileId
      }
    },
    closeCreateProfile() {
      this.state.dialogs.createProfile = false
      this.state.error.createProfile = ''
    },
    closeSettings() {
      this.state.dialogs.settings = false
      this.state.error.settings = ''
    },
    clearSelectedProfileState() {
      this.state.selectedProfileId = ''
      this.state.selectedProfile = null
      resetSteamCards(this.state)
    },
    async loadSteamForProfile(profileId) {
      this.state.loading.steam = true
      this.state.error.steam = ''

      try {
        const steamCards = await loadSteamCards(profileId)
        if (!this.isSelectedProfile(profileId)) {
          return
        }

        this.state.steamOverview = steamCards.overview
        this.state.steamDeals = steamCards.deals
        this.state.error.steam = steamCards.error
      } finally {
        if (this.isSelectedProfile(profileId)) {
          this.state.loading.steam = false
        }
      }
    },
    async loadConversationForProfile(profileId, chatSession) {
      try {
        const context = await loadProfileContext(profileId)
        if (this.isSelectedProfile(profileId)) {
          this.state.selectedProfile = context.profile
        }
        if (!chatSession.sending) {
          chatSession.messages = context.messages
        }
        chatSession.error = context.error
      } finally {
        chatSession.loading = false
      }
    },
    async loadProfiles(selectProfileId) {
      this.state.loading.profiles = true
      this.state.error.profiles = ''

      try {
        await this.refreshProfileSummaries(selectProfileId)
        const profiles = this.state.profiles

        const nextSelectedId =
          selectProfileId ||
          this.state.selectedProfileId ||
          (profiles.length ? profiles[0].id : '')

        if (nextSelectedId) {
          await this.handleProfileSelect(nextSelectedId)
        } else {
          this.clearSelectedProfileState()
        }
      } catch (error) {
        this.state.error.profiles = normalizeError(error)
      } finally {
        this.state.loading.profiles = false
      }
    },
    async handleProfileSelect(profileId) {
      if (!profileId) {
        return
      }

      const chatSession = ensureChatSession(this.state, profileId)
      this.state.selectedProfileId = profileId
      chatSession.loading = true
      chatSession.error = ''

      // Load conversation data and Steam data independently.
      // Conversation (profile + messages) must render immediately;
      // slow Steam API calls must not block it.
      const loadConversation = this.loadConversationForProfile(profileId, chatSession)
      const loadSteam = this.loadSteamForProfile(profileId)

      await Promise.all([loadConversation, loadSteam])
    },
    async handleCreateProfile(displayName) {
      this.state.loading.createProfile = true
      this.state.error.createProfile = ''

      try {
        const response = await createProfile(displayName)
        const profile = response.data.profile
        this.state.dialogs.createProfile = false
        await this.loadProfiles(profile.id)
        this.state.dialogs.settings = true
      } catch (error) {
        this.state.error.createProfile = normalizeError(error)
      } finally {
        this.state.loading.createProfile = false
      }
    },
    async handleDeleteProfile() {
      if (!this.state.selectedProfileId || !this.state.selectedProfile) {
        return
      }

      const displayName = this.state.selectedProfile.displayName
      const confirmed = window.confirm(`确认删除用户“${displayName}”吗？这会移除该用户的本地聊天记录和配置。`)
      if (!confirmed) {
        return
      }

      this.state.loading.profiles = true
      this.state.error.profiles = ''

      const nextProfile = this.state.profiles.find(
        (profile) => profile.id !== this.state.selectedProfileId
      )

      try {
        const deletedProfileId = this.state.selectedProfileId
        await deleteProfile(deletedProfileId)
        deleteChatSession(this.state, deletedProfileId)
        this.closeSettings()
        if (nextProfile) {
          await this.loadProfiles(nextProfile.id)
        } else {
          await this.refreshProfileSummaries('')
          this.clearSelectedProfileState()
        }
      } catch (error) {
        this.state.error.profiles = normalizeError(error)
      } finally {
        this.state.loading.profiles = false
      }
    },
    async handleSaveSettings(payload) {
      if (!this.state.selectedProfileId) {
        return
      }

      const validationError = validateProfileSettings(payload)
      if (validationError) {
        this.state.error.settings = validationError
        return
      }

      this.state.loading.saveSettings = true
      this.state.error.settings = ''

      try {
        const response = await updateProfileConfig(this.state.selectedProfileId, payload)
        this.state.selectedProfile = response.data.profile
        this.state.dialogs.settings = false
        await Promise.all([
          this.refreshProfileSummaries(this.state.selectedProfileId),
          this.refreshSteamData(),
        ])
      } catch (error) {
        this.state.error.settings = normalizeError(error)
      } finally {
        this.state.loading.saveSettings = false
      }
    },
    async handleSendMessage(question) {
      if (!this.state.selectedProfileId) {
        return
      }

      const profileId = this.state.selectedProfileId
      await sendProfileMessage(this.state, profileId, question, {
        onDone: () => this.refreshProfileSummaries(),
      })
    },
    async refreshSteamData() {
      if (!this.state.selectedProfileId) {
        return
      }

      const profileId = this.state.selectedProfileId
      await this.loadSteamForProfile(profileId)
    },
  },
}
</script>

<style lang="less">
:root {
  color-scheme: light;
  --app-height: 100vh;
}

* {
  box-sizing: border-box;
}

html,
body,
#app {
  min-height: 100%;
  width: 100%;
  max-width: 100%;
}

body {
  margin: 0;
  font-family: -apple-system, BlinkMacSystemFont, "SF Pro Display", "SF Pro Text", "Helvetica Neue", sans-serif;
  color: #102542;
  background: #eef4fb;
  overflow-x: hidden;
}

button,
input,
textarea {
  font: inherit;
}

a {
  color: inherit;
}

#app {
  position: relative;
  min-height: var(--app-height, 100vh);
  width: 100%;
  max-width: 100vw;
  overflow: hidden;
  padding: 24px;
}

.background {
  position: absolute;
  border-radius: 999px;
  filter: blur(18px);
  opacity: 0.6;
  pointer-events: none;
}

.background--top {
  width: 360px;
  height: 360px;
  top: -120px;
  right: -80px;
  background: radial-gradient(circle, rgba(88, 152, 255, 0.42), rgba(88, 152, 255, 0));
}

.background--bottom {
  width: 420px;
  height: 420px;
  left: -160px;
  bottom: -160px;
  background: radial-gradient(circle, rgba(255, 211, 179, 0.45), rgba(255, 211, 179, 0));
}

.shell {
  position: relative;
  z-index: 1;
  display: grid;
  grid-template-columns: 280px minmax(0, 1fr) 360px;
  gap: 18px;
  height: calc(var(--app-height, 100vh) - 48px);
  min-height: 0;
}

.panel {
  padding: 22px;
  border-radius: 34px;
  background: rgba(255, 255, 255, 0.54);
  backdrop-filter: blur(26px);
  border: 1px solid rgba(255, 255, 255, 0.42);
  box-shadow: 0 24px 60px rgba(13, 42, 78, 0.12);
  animation: float-in 0.5s ease both;
  min-height: 0;
}

.panel--sidebar {
  animation-delay: 0.02s;
  overflow: auto;
}

.panel--chat {
  animation-delay: 0.08s;
  display: flex;
  flex-direction: column;
  min-height: 0;
  overflow: hidden;
}

.panel--steam {
  animation-delay: 0.14s;
  overflow: auto;
}

.steam-stack {
  display: grid;
  gap: 18px;
}

.steam-drawer-toggle {
  position: fixed;
  right: 24px;
  bottom: 24px;
  z-index: 33;
  display: grid;
  gap: 2px;
  border: 0;
  border-radius: 22px;
  padding: 12px 18px;
  background: linear-gradient(135deg, #3d7eff, #5b8cff);
  color: #fff;
  text-align: left;
  cursor: pointer;
  box-shadow: 0 18px 34px rgba(61, 126, 255, 0.28);
}

.steam-drawer-toggle span {
  font-size: 11px;
  letter-spacing: 0.12em;
  text-transform: uppercase;
  opacity: 0.78;
}

.steam-drawer-toggle strong {
  font-size: 15px;
}

.steam-drawer-backdrop {
  position: fixed;
  inset: 0;
  z-index: 34;
  background: rgba(10, 22, 40, 0.22);
  backdrop-filter: blur(8px);
}

.device-desktop .steam-drawer-backdrop {
  display: none;
}

.steam-drawer {
  position: fixed;
  z-index: 35;
  top: 24px;
  right: 24px;
  bottom: 24px;
  width: min(380px, calc(100vw - 48px));
  padding: 20px;
  border-radius: 34px;
  background: rgba(247, 251, 255, 0.92);
  backdrop-filter: blur(26px);
  border: 1px solid rgba(255, 255, 255, 0.56);
  box-shadow: 0 28px 70px rgba(13, 42, 78, 0.18);
  transform: translateX(calc(100% + 48px));
  transition: transform 0.24s ease;
  overflow: auto;
}

.steam-drawer--open {
  transform: translateX(0);
}

.steam-drawer__header {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  gap: 12px;
  margin-bottom: 16px;
}

.steam-drawer .eyebrow {
  margin: 0 0 6px;
  color: rgba(35, 56, 102, 0.64);
  font-size: 12px;
  letter-spacing: 0.12em;
  text-transform: uppercase;
}

.steam-drawer h2 {
  margin: 0;
  color: #102542;
  font-size: 24px;
}

.steam-drawer__close {
  border: 0;
  border-radius: 16px;
  padding: 10px 14px;
  background: rgba(235, 241, 251, 0.88);
  color: #274062;
  cursor: pointer;
}

.floating-error {
  position: fixed;
  top: 18px;
  right: 18px;
  z-index: 50;
  margin: 0;
  padding: 12px 16px;
  max-width: 360px;
  border-radius: 18px;
  background: rgba(255, 120, 120, 0.94);
  color: #fff;
  box-shadow: 0 16px 30px rgba(163, 59, 68, 0.22);
}

.floating-error--bottom {
  top: auto;
  bottom: 18px;
}

.floating-error--bottom-secondary {
  top: auto;
  bottom: 84px;
}

@keyframes float-in {
  from {
    opacity: 0;
    transform: translateY(18px) scale(0.98);
  }
  to {
    opacity: 1;
    transform: translateY(0) scale(1);
  }
}

@media (max-width: 1240px) {
  .shell {
    grid-template-columns: 260px minmax(0, 1fr);
  }

  .panel--steam {
    grid-column: 1 / -1;
  }
}

@media (max-width: 960px) {
  #app {
    padding: 16px;
    overflow: auto;
  }

  .shell {
    grid-template-columns: 1fr;
    height: auto;
  }

  .panel {
    min-height: auto;
  }

  .panel--chat {
    min-height: 60vh;
  }
}

#app.device-tablet {
  min-height: var(--app-height, 100vh);
  width: 100%;
  max-width: 100vw;
  overflow: hidden;
  padding: 18px;
}

.device-tablet .shell {
  grid-template-columns: 260px minmax(0, 1fr);
  gap: 16px;
  height: calc(var(--app-height, 100vh) - 36px);
  min-width: 0;
  overflow: hidden;
}

.device-tablet .panel {
  padding: 20px;
  min-width: 0;
  max-width: 100%;
}

.device-tablet .panel--sidebar,
.device-tablet .panel--chat {
  min-height: 0;
  overflow: hidden;
}

.device-tablet .sidebar {
  min-width: 0;
  overflow: hidden;
}

.device-tablet .profile-list {
  min-height: 0;
  overflow: auto;
}

.device-tablet .chat-pane {
  min-width: 0;
  height: 100%;
}

.device-tablet .message-list {
  min-height: 0;
}

.device-tablet .steam-drawer-toggle {
  right: 18px;
  bottom: calc(18px + env(safe-area-inset-bottom));
}

.device-tablet .steam-drawer {
  top: 18px;
  right: 18px;
  bottom: calc(18px + env(safe-area-inset-bottom));
  width: min(420px, calc(100vw - 36px));
}

#app.device-mobile {
  min-height: var(--app-height, 100vh);
  width: 100%;
  max-width: 100vw;
  overflow-x: hidden;
  overflow-y: auto;
  padding: 8px 8px calc(8px + env(safe-area-inset-bottom));
  overscroll-behavior-x: none;
}

.device-mobile .background {
  display: none;
}

.device-mobile .shell {
  grid-template-columns: 1fr;
  grid-template-rows: auto minmax(0, 1fr);
  gap: 8px;
  height: calc(var(--app-height, 100vh) - 16px - env(safe-area-inset-bottom));
  width: 100%;
  max-width: 100%;
  min-width: 0;
  overflow: hidden;
}

.device-mobile .panel {
  padding: 10px;
  border-radius: 22px;
  min-height: auto;
  min-width: 0;
  width: 100%;
  max-width: 100%;
  box-shadow: 0 16px 36px rgba(13, 42, 78, 0.1);
}

.device-mobile .panel--sidebar,
.device-mobile .panel--steam {
  overflow: hidden;
}

.device-mobile .panel--chat {
  height: auto;
  min-height: 0;
  max-height: none;
  overflow: hidden;
}

.device-mobile .steam-stack {
  gap: 12px;
  min-width: 0;
  width: 100%;
  max-width: 100%;
}

.device-mobile .steam-drawer-toggle {
  right: 12px;
  bottom: calc(12px + env(safe-area-inset-bottom));
  border-radius: 18px;
  padding: 10px 14px;
}

.device-mobile .steam-drawer {
  top: 10px;
  right: 10px;
  bottom: calc(10px + env(safe-area-inset-bottom));
  width: min(360px, calc(100vw - 20px));
  padding: 16px;
  border-radius: 28px;
}

.device-mobile .steam-drawer h2 {
  font-size: 21px;
}

.device-mobile .floating-error {
  top: 10px;
  left: 10px;
  right: 10px;
  max-width: none;
}

.device-mobile .floating-error--bottom,
.device-mobile .floating-error--bottom-secondary {
  top: auto;
  bottom: calc(12px + env(safe-area-inset-bottom));
}

.device-mobile .floating-error--bottom-secondary {
  bottom: calc(76px + env(safe-area-inset-bottom));
}

.device-mobile .sidebar {
  gap: 8px;
  min-width: 0;
  width: 100%;
  max-width: 100%;
  overflow: hidden;
}

.device-mobile .sidebar__header {
  align-items: center;
  min-width: 0;
}

.device-mobile .sidebar h1,
.device-mobile .chat-pane h2,
.device-mobile .dialog h2 {
  font-size: 18px;
}

.device-mobile .sidebar .eyebrow,
.device-mobile .chat-pane .eyebrow {
  display: none;
}

.device-mobile .glass-button,
.device-mobile .danger-button,
.device-mobile .primary-button,
.device-mobile .secondary-button,
.device-mobile .ghost-button,
.device-mobile .refresh-button {
  padding: 8px 10px;
  border-radius: 12px;
  font-size: 13px;
}

.device-mobile .profile-list {
  flex-direction: row;
  gap: 8px;
  width: 100%;
  max-width: 100%;
  min-width: 0;
  overflow-x: auto;
  overflow-y: hidden;
  padding: 0;
  scroll-snap-type: x proximity;
  scrollbar-width: none;
  overscroll-behavior-x: contain;
  -webkit-overflow-scrolling: touch;
}

.device-mobile .profile-list::-webkit-scrollbar {
  display: none;
}

.device-mobile .profile-card {
  flex: 0 0 100%;
  width: 100%;
  min-width: 0;
  max-width: 100%;
  padding: 9px 12px;
  border-radius: 16px;
  box-shadow: 0 8px 18px rgba(18, 52, 89, 0.08);
  scroll-snap-align: start;
}

.device-mobile .profile-card:hover {
  transform: none;
}

.device-mobile .profile-card__top {
  align-items: flex-start;
  min-width: 0;
  margin-bottom: 0;
}

.device-mobile .profile-card__top strong,
.device-mobile .profile-card p {
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.device-mobile .profile-card__badge {
  flex: 0 0 auto;
}

.device-mobile .sidebar__footer {
  display: none;
}

.device-mobile .profile-card p,
.device-mobile .profile-card__meta {
  display: none;
}

.device-mobile .chat-pane {
  gap: 8px;
  min-width: 0;
  width: 100%;
  max-width: 100%;
}

.device-mobile .chat-pane__header {
  gap: 8px;
  min-width: 0;
}

.device-mobile .chat-pane__header > div {
  min-width: 0;
}

.device-mobile .chat-pane h2 {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.device-mobile .error-banner {
  padding: 8px 10px;
  border-radius: 14px;
  font-size: 13px;
  overflow-wrap: anywhere;
  word-break: break-word;
}

.device-mobile .knowledge-section,
.device-mobile .knowledge-body,
.device-mobile .knowledge-list,
.device-mobile .knowledge-item,
.device-mobile .knowledge-drop-zone {
  min-width: 0;
  width: 100%;
  max-width: 100%;
}

.device-mobile .knowledge-section {
  padding: 7px 10px;
  border-radius: 14px;
  overflow: hidden;
}

.device-mobile .knowledge-header {
  min-width: 0;
  gap: 8px;
  min-height: 26px;
}

.device-mobile .knowledge-title {
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.device-mobile .knowledge-item__name {
  min-width: 0;
}

.device-mobile .knowledge-item__tag,
.device-mobile .knowledge-item__delete {
  flex: 0 0 auto;
}

.device-mobile .message-list {
  gap: 8px;
  padding: 4px 2px 4px 0;
  min-width: 0;
  width: 100%;
  max-width: 100%;
}

.device-mobile .message-bubble {
  min-width: 0;
  max-width: 94%;
  padding: 11px 12px;
  border-radius: 18px;
}

.device-mobile .message-body {
  font-size: 14px;
  line-height: 1.65;
  max-width: 100%;
  overflow-wrap: anywhere;
  word-break: break-word;
}

.device-mobile .message-body * {
  max-width: 100%;
  overflow-wrap: anywhere;
  word-break: break-word;
}

.device-mobile .message-body pre,
.device-mobile .message-body code {
  white-space: pre-wrap;
}

.device-mobile .message-body table {
  display: block;
  overflow-x: auto;
}

.device-mobile .message-label {
  margin-bottom: 8px;
  font-size: 11px;
}

.device-mobile .loading-bubble {
  padding: 13px 14px;
  border-radius: 20px;
}

.device-mobile .composer {
  grid-template-columns: minmax(0, 1fr) auto;
  gap: 7px;
  padding: 8px;
  border-radius: 18px;
  bottom: calc(8px + env(safe-area-inset-bottom));
  min-width: 0;
  width: 100%;
  max-width: 100%;
}

.device-mobile .composer__input {
  min-height: 40px;
  max-height: 96px;
  border-radius: 14px;
  padding: 10px 12px;
}

.device-mobile .composer__button {
  width: auto;
  min-width: 72px;
  height: 40px;
  border-radius: 14px;
  padding: 0 12px;
}

.device-mobile .overlay,
.device-mobile .sheet-overlay {
  place-items: end center;
  padding: 0 10px calc(10px + env(safe-area-inset-bottom));
}

.device-mobile .dialog,
.device-mobile .sheet {
  width: 100%;
  max-height: calc(var(--app-height, 100vh) - 20px);
  overflow: auto;
  padding: 22px 18px calc(18px + env(safe-area-inset-bottom));
  border-radius: 28px 28px 0 0;
}

.device-mobile .dialog__header,
.device-mobile .dialog__footer,
.device-mobile .sheet__header,
.device-mobile .sheet__footer {
  align-items: flex-start;
}

.device-mobile .dialog__footer,
.device-mobile .sheet__footer {
  gap: 10px;
}

.device-mobile .dialog__footer .secondary-button,
.device-mobile .dialog__footer .primary-button,
.device-mobile .sheet__footer .secondary-button,
.device-mobile .sheet__footer .primary-button {
  flex: 1;
}

.device-mobile .sheet__body {
  grid-template-columns: 1fr;
  gap: 14px;
  padding-right: 0;
}

.device-mobile .section,
.device-mobile .card {
  padding: 16px;
  border-radius: 24px;
  min-width: 0;
  width: 100%;
  max-width: 100%;
}

.device-mobile .card__header {
  margin-bottom: 14px;
  min-width: 0;
}

.device-mobile .card h3 {
  font-size: 19px;
}

.device-mobile .hero {
  grid-template-columns: 56px minmax(0, 1fr);
  gap: 12px;
  min-width: 0;
}

.device-mobile .hero img {
  width: 56px;
  height: 56px;
  border-radius: 18px;
}

.device-mobile .stats {
  grid-template-columns: 1fr;
  gap: 10px;
}

.device-mobile .deal-item {
  grid-template-columns: 72px minmax(0, 1fr);
  gap: 10px;
  padding: 10px;
  border-radius: 18px;
  min-width: 0;
  max-width: 100%;
}

.device-mobile .deal-item img {
  width: 72px;
  height: 48px;
  border-radius: 14px;
}

.device-mobile .deal-item__title,
.device-mobile .deal-item__price {
  gap: 8px;
  min-width: 0;
  flex-wrap: wrap;
}

.device-mobile .game-card,
.device-mobile .current-game,
.device-mobile .stat {
  min-width: 0;
  max-width: 100%;
}

.device-mobile .deal-item strong,
.device-mobile .game-card strong,
.device-mobile .hero strong,
.device-mobile .current-game strong,
.device-mobile .stat strong {
  overflow-wrap: anywhere;
  word-break: break-word;
}

@media (max-width: 380px) {
  .device-mobile .shell {
    gap: 10px;
  }
}

@media (max-width: 360px) {
  .device-mobile .composer {
    grid-template-columns: 1fr;
  }

  .device-mobile .composer__button {
    width: 100%;
  }
}
</style>
