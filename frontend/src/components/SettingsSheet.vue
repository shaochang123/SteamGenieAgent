<template>
  <transition name="sheet">
    <div v-if="visible" class="sheet-overlay" @click.self="$emit('close')">
      <div class="sheet">
        <div class="sheet__header">
          <div>
            <p class="eyebrow">当前用户配置</p>
            <h2>{{ profile ? profile.displayName : '未选择用户' }}</h2>
          </div>
          <button class="ghost-button" type="button" @click="$emit('close')">
            关闭
          </button>
        </div>

        <div v-if="draft" class="sheet__body">
          <section class="section">
            <div class="section__title">
              <strong>AI 接入方式</strong>
              <span>必须在本地 Ollama 和 OpenAI Key 中二选一</span>
            </div>

            <div class="segmented">
              <button
                v-for="option in providerOptions"
                :key="option.value"
                type="button"
                :class="{ active: draft.ai.provider === option.value }"
                @click="draft.ai.provider = option.value"
              >
                {{ option.label }}
              </button>
            </div>

            <p class="provider-hint">
              {{
                draft.ai.provider === 'ollama'
                  ? '当前用户将使用本地 Ollama 服务。'
                  : '当前用户将使用 OpenAI 兼容接口和 API Key。'
              }}
            </p>

            <label v-for="field in aiFields" :key="field.key" class="field">
              <span>{{ field.label }}</span>
              <input
                v-model.trim="draft.ai[field.group][field.key]"
                :type="field.type"
                :placeholder="field.placeholder"
              >
            </label>
          </section>

          <section class="section">
            <div class="section__title">
              <strong>Steam 凭据</strong>
              <span>用于个人数据和商店卡片</span>
            </div>

            <label v-for="field in steamFields" :key="field.key" class="field">
              <span>{{ field.label }}</span>
              <input
                v-model.trim="draft.steam[field.key]"
                :type="field.type"
                :placeholder="field.placeholder"
              >
              <span v-if="field.hint" class="field-hint">{{ field.hint }}</span>
            </label>
          </section>
        </div>

        <div class="sheet__footer">
          <button class="secondary-button" type="button" @click="$emit('close')">
            取消
          </button>
          <button class="primary-button" type="button" :disabled="saving || !draft" @click="submit">
            {{ saving ? '保存中...' : '保存设置' }}
          </button>
        </div>
      </div>
    </div>
  </transition>
</template>

<script>
const PROVIDER_OPTIONS = [
  { value: 'ollama', label: 'Ollama' },
  { value: 'openai-compatible', label: 'OpenAI 兼容' },
]

const OLLAMA_FIELDS = [
  { group: 'ollama', key: 'baseUrl', label: 'Ollama Base URL', type: 'text', placeholder: 'http://127.0.0.1:11434' },
  { group: 'ollama', key: 'model', label: 'Ollama Model', type: 'text', placeholder: 'qwen3:8b' },
]

const OPENAI_FIELDS = [
  { group: 'openaiCompatible', key: 'apiKey', label: 'API Key', type: 'password', placeholder: 'sk-...' },
  { group: 'openaiCompatible', key: 'baseUrl', label: 'Base URL', type: 'text', placeholder: 'https://api.openai.com/v1' },
  { group: 'openaiCompatible', key: 'model', label: 'Model', type: 'text', placeholder: 'gpt-4.1-mini' },
]

const STEAM_FIELDS = [
  { key: 'apiKey', label: 'Steam API Key', type: 'password', placeholder: 'Steam Web API Key' },
  { key: 'steamId', label: 'SteamID64', type: 'text', placeholder: '7656119...' },
  { key: 'steamPath', label: 'Steam Install Path', type: 'text', placeholder: 'D:\\steam', hint: '本地 Steam 安装目录' },
  { key: 'country', label: 'Country', type: 'text', placeholder: 'CN' },
  { key: 'language', label: 'Language', type: 'text', placeholder: 'zh-CN' },
  { key: 'proxy', label: 'HTTP 代理 (Proxy)', type: 'text', placeholder: 'http://127.0.0.1:7890', hint: '用于访问 Steam API 的代理地址，留空则不使用代理' },
]

function normalizeProfile(profile) {
  if (!profile) {
    return null
  }

  return {
    ai: {
      provider: profile.ai?.provider || 'ollama',
      ollama: {
        baseUrl: profile.ai?.ollama?.baseUrl || 'http://127.0.0.1:11434',
        model: profile.ai?.ollama?.model || 'qwen3:8b',
      },
      openaiCompatible: {
        apiKey: profile.ai?.openaiCompatible?.apiKey || '',
        baseUrl: profile.ai?.openaiCompatible?.baseUrl || 'https://api.openai.com/v1',
        model: profile.ai?.openaiCompatible?.model || 'gpt-4.1-mini',
      },
    },
    steam: {
      apiKey: profile.steam?.apiKey || '',
      steamId: profile.steam?.steamId || '',
      steamPath: profile.steam?.steamPath || '',
      country: profile.steam?.country || 'CN',
      language: profile.steam?.language || 'zh-CN',
      proxy: profile.steam?.proxy || '',
    },
  }
}

export default {
  name: 'SettingsSheet',
  props: {
    visible: {
      type: Boolean,
      default: false,
    },
    profile: {
      type: Object,
      default: null,
    },
    saving: {
      type: Boolean,
      default: false,
    },
  },
  data() {
    return {
      draft: null,
    }
  },
  watch: {
    visible: {
      immediate: true,
      handler(nextValue) {
        if (nextValue) {
          this.resetDraft()
        }
      },
    },
    profile: {
      deep: true,
      handler() {
        if (this.visible) {
          this.resetDraft()
        }
      },
    },
  },
  computed: {
    providerOptions() {
      return PROVIDER_OPTIONS
    },
    aiFields() {
      return this.draft?.ai.provider === 'ollama' ? OLLAMA_FIELDS : OPENAI_FIELDS
    },
    steamFields() {
      return STEAM_FIELDS
    },
  },
  methods: {
    resetDraft() {
      this.draft = normalizeProfile(this.profile)
    },
    submit() {
      if (!this.draft) {
        return
      }
      this.$emit('save', JSON.parse(JSON.stringify(this.draft)))
    },
  },
}
</script>

<style lang="less" scoped>
.sheet-enter-active,
.sheet-leave-active {
  transition: opacity 0.22s ease;
}

.sheet-enter,
.sheet-leave-to {
  opacity: 0;
}

.sheet-overlay {
  position: fixed;
  inset: 0;
  z-index: 40;
  display: grid;
  place-items: center;
  background: rgba(10, 22, 40, 0.18);
  backdrop-filter: blur(14px);
  padding: 24px;
}

.sheet {
  width: min(920px, calc(100vw - 48px));
  max-height: min(92vh, 920px);
  padding: 28px 28px 24px;
  border-radius: 32px;
  background: linear-gradient(180deg, rgba(255, 255, 255, 0.96), rgba(245, 249, 255, 0.94));
  box-shadow: 0 24px 64px rgba(13, 42, 78, 0.18);
  display: flex;
  flex-direction: column;
}

.sheet__header,
.sheet__footer {
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 12px;
}

.sheet__body {
  margin-top: 22px;
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 20px;
  overflow: auto;
  padding-right: 6px;
}

.eyebrow {
  margin: 0 0 6px;
  color: rgba(35, 56, 102, 0.64);
  font-size: 12px;
  letter-spacing: 0.12em;
  text-transform: uppercase;
}

h2 {
  margin: 0;
  color: #102542;
}

.section {
  padding: 20px;
  border-radius: 26px;
  background: rgba(255, 255, 255, 0.82);
  box-shadow: inset 0 1px 0 rgba(255, 255, 255, 0.72);
}

.section__title {
  display: flex;
  flex-direction: column;
  gap: 4px;
  margin-bottom: 14px;
  color: #102542;
}

.section__title span {
  color: #607086;
  font-size: 13px;
}

.segmented {
  display: inline-grid;
  grid-template-columns: repeat(2, 1fr);
  padding: 4px;
  border-radius: 18px;
  background: rgba(235, 241, 251, 0.84);
  margin-bottom: 14px;
}

.segmented button {
  border: 0;
  border-radius: 14px;
  padding: 10px 16px;
  background: transparent;
  color: #506177;
  cursor: pointer;
}

.segmented button.active {
  background: #fff;
  color: #3656d8;
  box-shadow: 0 10px 18px rgba(61, 126, 255, 0.12);
}

.provider-hint {
  margin: 0 0 2px;
  color: #607086;
  font-size: 13px;
  line-height: 1.6;
}

.field {
  display: grid;
  gap: 8px;
  margin-top: 14px;
}

.field span {
  color: #274062;
  font-size: 14px;
}

.field input {
  border: 1px solid rgba(70, 99, 140, 0.14);
  border-radius: 18px;
  padding: 14px 16px;
  font-size: 15px;
  background: rgba(248, 250, 255, 0.9);
}

.field input:focus {
  outline: none;
  border-color: rgba(61, 126, 255, 0.4);
  box-shadow: 0 0 0 4px rgba(61, 126, 255, 0.12);
}

.field-hint {
  color: #8a99ae;
  font-size: 12px;
  margin-top: -2px;
}

.sheet__footer {
  margin-top: 22px;
}

.ghost-button,
.secondary-button,
.primary-button {
  border: 0;
  border-radius: 16px;
  padding: 12px 16px;
  cursor: pointer;
}

.ghost-button,
.secondary-button {
  background: rgba(235, 241, 251, 0.8);
  color: #274062;
}

.primary-button {
  background: linear-gradient(135deg, #3d7eff, #5b8cff);
  color: #fff;
  box-shadow: 0 18px 26px rgba(61, 126, 255, 0.24);
}

.primary-button:disabled {
  opacity: 0.55;
  cursor: not-allowed;
}

@media (max-width: 820px) {
  .sheet-overlay {
    padding: 16px;
  }

  .sheet {
    padding: 22px 18px 18px;
    width: min(920px, calc(100vw - 32px));
  }

  .sheet__body {
    grid-template-columns: 1fr;
  }
}
</style>
