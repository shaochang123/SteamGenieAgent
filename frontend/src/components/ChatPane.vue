<template>
  <section class="chat-pane">
    <header class="chat-pane__header">
      <div>
        <p class="eyebrow">会话</p>
        <h2>{{ title }}</h2>
      </div>
      <button class="ghost-button" type="button" :disabled="!profile" @click="$emit('open-settings')">
        设置
      </button>
    </header>

    <p v-if="error" class="error-banner">{{ error }}</p>

    <KnowledgeUploader v-if="profile" :profile-id="profile.id" />

    <MessageList :messages="messages" :loading="sending" :streaming-content="streamingContent" />

    <ChatComposer
      :disabled="!profile || loading || sending"
      :loading="sending"
      @send="$emit('send-message', $event)"
    />
  </section>
</template>

<script>
import ChatComposer from './ChatComposer.vue'
import KnowledgeUploader from './KnowledgeUploader.vue'
import MessageList from './MessageList.vue'

export default {
  name: 'ChatPane',
  components: {
    ChatComposer,
    KnowledgeUploader,
    MessageList,
  },
  props: {
    profile: {
      type: Object,
      default: null,
    },
    messages: {
      type: Array,
      default: () => [],
    },
    loading: {
      type: Boolean,
      default: false,
    },
    sending: {
      type: Boolean,
      default: false,
    },
    error: {
      type: String,
      default: '',
    },
    streamingContent: {
      type: String,
      default: '',
    },
  },
  computed: {
    title() {
      return this.profile ? this.profile.displayName : '请选择一个用户'
    },
  },
}
</script>

<style lang="less" scoped>
.chat-pane {
  display: flex;
  flex-direction: column;
  gap: 18px;
  height: 100%;
  min-height: 0;
}

.chat-pane__header {
  display: flex;
  justify-content: space-between;
  gap: 12px;
  align-items: center;
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
  font-size: 28px;
}

.ghost-button {
  border: 0;
  border-radius: 16px;
  padding: 12px 16px;
  background: rgba(255, 255, 255, 0.82);
  color: #274062;
  cursor: pointer;
  box-shadow: 0 10px 24px rgba(18, 52, 89, 0.12);
}

.ghost-button:disabled {
  opacity: 0.45;
  cursor: not-allowed;
}

.error-banner {
  margin: 0;
  padding: 12px 14px;
  border-radius: 18px;
  background: rgba(255, 120, 120, 0.12);
  color: #a33b44;
  flex: 0 0 auto;
}
</style>
