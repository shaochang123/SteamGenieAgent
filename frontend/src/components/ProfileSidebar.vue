<template>
  <aside class="sidebar">
    <div class="sidebar__header">
      <div>
        <p class="eyebrow">Steam Agent</p>
        <h1>Steam Desk</h1>
      </div>
      <button class="glass-button" type="button" @click="$emit('create-profile')">
        新建用户
      </button>
    </div>

    <div v-if="profiles.length" class="profile-list">
      <button
        v-for="profile in profiles"
        :key="profile.id"
        class="profile-card"
        :class="{ 'profile-card--active': profile.id === selectedProfileId }"
        type="button"
        @click="$emit('select-profile', profile.id)"
      >
        <div class="profile-card__top">
          <strong>{{ profile.displayName }}</strong>
          <span class="profile-card__badge">{{ providerLabel(profile.provider) }}</span>
        </div>
        <p>{{ Math.floor(profile.messageCount / 2) }} 条消息</p>
        <div class="profile-card__meta">
          <span :class="profile.hasAiConfig ? 'ok' : 'warn'">
            {{ profile.hasAiConfig ? 'AI 已配置' : 'AI 待配置' }}
          </span>
          <span :class="profile.hasSteamConfig ? 'ok' : 'warn'">
            {{ profile.hasSteamConfig ? 'Steam 已配置' : 'Steam 待配置' }}
          </span>
        </div>
      </button>
    </div>

    <div v-else class="empty-state">
      <p>还没有本地用户档案。</p>
      <button class="primary-button" type="button" @click="$emit('create-profile')">
        创建第一个用户
      </button>
    </div>

    <div v-if="selectedProfileId" class="sidebar__footer">
      <button
        class="danger-button"
        type="button"
        @click="$emit('delete-profile')"
      >
        删除当前用户
      </button>
    </div>
  </aside>
</template>

<script>
export default {
  name: 'ProfileSidebar',
  props: {
    profiles: {
      type: Array,
      default: () => [],
    },
    selectedProfileId: {
      type: String,
      default: '',
    },
  },
  methods: {
    providerLabel(provider) {
      return provider === 'openai-compatible' ? 'OpenAI' : 'Ollama'
    },
  },
}
</script>

<style lang="less" scoped>
.sidebar {
  display: flex;
  flex-direction: column;
  gap: 20px;
  height: 100%;
}

.sidebar__header,
.sidebar__footer {
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 12px;
}

.eyebrow {
  margin: 0 0 6px;
  color: rgba(35, 56, 102, 0.64);
  font-size: 12px;
  letter-spacing: 0.12em;
  text-transform: uppercase;
}

h1 {
  margin: 0;
  font-size: 28px;
  line-height: 1;
  color: #102542;
}

.profile-list {
  display: flex;
  flex-direction: column;
  gap: 12px;
  overflow: auto;
  padding-right: 4px;
}

.profile-card {
  border: 0;
  width: 100%;
  text-align: left;
  padding: 16px;
  border-radius: 22px;
  background: rgba(255, 255, 255, 0.72);
  box-shadow: 0 14px 32px rgba(18, 52, 89, 0.12);
  transition: transform 0.2s ease, box-shadow 0.2s ease, border-color 0.2s ease;
  border: 1px solid transparent;
  cursor: pointer;
}

.profile-card:hover {
  transform: translateY(-1px);
  box-shadow: 0 18px 36px rgba(18, 52, 89, 0.16);
}

.profile-card--active {
  border-color: rgba(69, 113, 255, 0.26);
  background: linear-gradient(180deg, rgba(255, 255, 255, 0.92), rgba(232, 242, 255, 0.86));
}

.profile-card__top {
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 8px;
  margin-bottom: 8px;
  color: #102542;
}

.profile-card__badge {
  padding: 4px 10px;
  border-radius: 999px;
  background: rgba(69, 113, 255, 0.1);
  color: #3656d8;
  font-size: 12px;
}

.profile-card p {
  margin: 0 0 10px;
  color: #53657d;
  font-size: 14px;
}

.profile-card__meta {
  display: flex;
  gap: 8px;
  flex-wrap: wrap;
  font-size: 12px;
}

.ok,
.warn {
  padding: 4px 8px;
  border-radius: 999px;
  background: rgba(16, 37, 66, 0.06);
}

.ok {
  color: #227a52;
}

.warn {
  color: #b36b20;
}

.empty-state {
  display: grid;
  gap: 12px;
  padding: 28px 20px;
  border-radius: 24px;
  background: rgba(255, 255, 255, 0.62);
  color: #53657d;
}

.glass-button,
.danger-button,
.primary-button {
  border: 0;
  border-radius: 16px;
  font-size: 14px;
  padding: 12px 16px;
  cursor: pointer;
  transition: transform 0.18s ease, box-shadow 0.18s ease, opacity 0.18s ease;
}

.glass-button:hover,
.danger-button:hover,
.primary-button:hover {
  transform: translateY(-1px);
}

.glass-button {
  background: rgba(255, 255, 255, 0.82);
  color: #102542;
  box-shadow: 0 10px 24px rgba(18, 52, 89, 0.12);
}

.danger-button {
  width: 100%;
  background: rgba(255, 235, 238, 0.96);
  color: #b63d4b;
}

.primary-button {
  background: linear-gradient(135deg, #3d7eff, #5b8cff);
  color: #fff;
  box-shadow: 0 18px 26px rgba(61, 126, 255, 0.24);
}
</style>
