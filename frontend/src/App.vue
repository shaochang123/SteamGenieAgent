<template>
  <div id="app">
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

      <section class="panel panel--steam">
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
    }
  },
  async created() {
    await this.loadProfiles()
  },
  computed: {
    activeChatSession() {
      return activeChatSession(this.state)
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
}

* {
  box-sizing: border-box;
}

html,
body,
#app {
  min-height: 100%;
}

body {
  margin: 0;
  font-family: -apple-system, BlinkMacSystemFont, "SF Pro Display", "SF Pro Text", "Helvetica Neue", sans-serif;
  color: #102542;
  background: #eef4fb;
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
  min-height: 100vh;
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
  height: calc(100vh - 48px);
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
</style>
