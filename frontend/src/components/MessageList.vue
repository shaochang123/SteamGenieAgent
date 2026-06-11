<template>
  <div ref="scrollHost" class="message-list">
    <div v-if="!messages.length && !loading" class="empty-chat">
      <p class="empty-chat__title">从一个问题开始</p>
      <p class="empty-chat__text">这里会保留当前用户的独立聊天历史。</p>
    </div>

    <div
      v-for="(message, index) in messages"
      :key="message.timestamp || index"
      class="message-row"
      :class="message.role === 'assistant' ? 'message-row--assistant' : 'message-row--user'"
    >
      <div class="message-bubble">
        <p class="message-label">
          {{ message.role === 'tool_call' ? '工具调用' : message.role === 'tool_result' ? '工具结果' : message.role === 'assistant' ? 'AI' : '你' }}
        </p>
        <div v-if="message.role === 'tool_call' || message.role === 'tool_result'" class="message-body message-body--tool">
          {{ message.content }}
        </div>
        <div v-else class="message-body" v-html="renderMarkdown(message.content)"></div>
      </div>
    </div>

    <div v-if="loading && streamingContent" class="message-row message-row--assistant">
      <div class="message-bubble">
        <p class="message-label">AI</p>
        <div class="message-body" v-html="renderMarkdown(streamingContent)"></div>
      </div>
    </div>

    <div v-else-if="loading" class="loading-bubble">
      <span></span>
      <span></span>
      <span></span>
    </div>
  </div>
</template>

<script>
import MarkdownIt from 'markdown-it'

const markdown = new MarkdownIt({
  breaks: true,
  linkify: true,
})

export default {
  name: 'MessageList',
  props: {
    messages: {
      type: Array,
      default: () => [],
    },
    loading: {
      type: Boolean,
      default: false,
    },
    streamingContent: {
      type: String,
      default: '',
    },
  },
  watch: {
    messages: {
      handler() {
        this.scrollToBottom()
      },
      deep: true,
    },
    loading() {
      this.scrollToBottom()
    },
  },
  mounted() {
    this.scrollToBottom()
  },
  methods: {
    renderMarkdown(content) {
      return markdown.render(content || '')
    },
    scrollToBottom() {
      this.$nextTick(() => {
        const host = this.$refs.scrollHost
        if (host) {
          host.scrollTop = host.scrollHeight
        }
      })
    },
  },
}
</script>

<style lang="less" scoped>
.message-list {
  flex: 1;
  min-height: 0;
  overflow: auto;
  padding: 8px 6px 8px 0;
  display: flex;
  flex-direction: column;
  gap: 14px;
}

.empty-chat {
  margin: auto;
  max-width: 320px;
  text-align: center;
  color: #607086;
}

.empty-chat__title {
  margin: 0 0 8px;
  font-size: 20px;
  color: #102542;
}

.empty-chat__text {
  margin: 0;
  line-height: 1.6;
}

.message-row {
  display: flex;
}

.message-row--user {
  justify-content: flex-end;
}

.message-row--assistant {
  justify-content: flex-start;
}

.message-bubble {
  max-width: min(78%, 640px);
  padding: 16px 18px;
  border-radius: 24px;
  box-shadow: 0 16px 34px rgba(17, 45, 79, 0.08);
}

.message-row--assistant .message-bubble {
  background: rgba(255, 255, 255, 0.84);
  border-top-left-radius: 10px;
}

.message-row--user .message-bubble {
  background: linear-gradient(135deg, #3d7eff, #6ea2ff);
  color: #fff;
  border-top-right-radius: 10px;
}

.message-label {
  margin: 0 0 10px;
  font-size: 12px;
  letter-spacing: 0.08em;
  text-transform: uppercase;
  opacity: 0.72;
}

.message-body {
  font-size: 15px;
  line-height: 1.7;
}

.message-body /deep/ p {
  margin: 0 0 10px;
}

.message-body /deep/ p:last-child {
  margin-bottom: 0;
}

.message-body--tool {
  color: #607086;
  font-style: italic;
  font-size: 13px;
}

.message-body /deep/ a {
  color: inherit;
}

.loading-bubble {
  display: inline-flex;
  align-items: center;
  gap: 8px;
  width: fit-content;
  padding: 16px 18px;
  background: rgba(255, 255, 255, 0.84);
  border-radius: 24px;
  box-shadow: 0 16px 34px rgba(17, 45, 79, 0.08);
}

.loading-bubble span {
  width: 8px;
  height: 8px;
  border-radius: 50%;
  background: #5d7392;
  animation: pulse 1.1s infinite ease-in-out;
}

.loading-bubble span:nth-child(2) {
  animation-delay: 0.15s;
}

.loading-bubble span:nth-child(3) {
  animation-delay: 0.3s;
}

@keyframes pulse {
  0%,
  100% {
    transform: translateY(0);
    opacity: 0.35;
  }
  50% {
    transform: translateY(-4px);
    opacity: 1;
  }
}

@media (max-width: 900px) {
  .message-bubble {
    max-width: 92%;
  }
}
</style>
