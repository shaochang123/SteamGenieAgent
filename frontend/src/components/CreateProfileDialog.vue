<template>
  <transition name="fade">
    <div v-if="visible" class="overlay" @click.self="$emit('close')">
      <div class="dialog">
        <div class="dialog__header">
          <div>
            <p class="eyebrow">新用户</p>
            <h2>创建本地会话档案</h2>
          </div>
          <button class="ghost-button" type="button" @click="$emit('close')">
            关闭
          </button>
        </div>

        <label class="field">
          <span>用户名</span>
          <input
            v-model.trim="draftName"
            type="text"
            maxlength="60"
            placeholder="例如：Alice"
            @keyup.enter="submit"
          >
        </label>

        <p class="hint">
          用户名只作为本地档案名使用。切换用户名时会切换到独立的聊天历史和配置。
        </p>

        <p v-if="error" class="error-text">{{ error }}</p>

        <div class="dialog__footer">
          <button class="secondary-button" type="button" @click="$emit('close')">
            取消
          </button>
          <button class="primary-button" type="button" :disabled="loading" @click="submit">
            {{ loading ? '创建中...' : '创建用户' }}
          </button>
        </div>
      </div>
    </div>
  </transition>
</template>

<script>
export default {
  name: 'CreateProfileDialog',
  props: {
    visible: {
      type: Boolean,
      default: false,
    },
    loading: {
      type: Boolean,
      default: false,
    },
    error: {
      type: String,
      default: '',
    },
  },
  data() {
    return {
      draftName: '',
    }
  },
  watch: {
    visible(nextValue) {
      if (nextValue) {
        this.draftName = ''
      }
    },
  },
  methods: {
    submit() {
      if (!this.draftName) {
        return
      }
      this.$emit('submit', this.draftName)
    },
  },
}
</script>

<style lang="less" scoped>
.fade-enter-active,
.fade-leave-active {
  transition: opacity 0.22s ease;
}

.fade-enter,
.fade-leave-to {
  opacity: 0;
}

.overlay {
  position: fixed;
  inset: 0;
  z-index: 30;
  display: grid;
  place-items: center;
  background: rgba(10, 22, 40, 0.22);
  backdrop-filter: blur(14px);
}

.dialog {
  width: min(480px, calc(100vw - 32px));
  border-radius: 28px;
  padding: 24px;
  background: linear-gradient(180deg, rgba(255, 255, 255, 0.96), rgba(245, 249, 255, 0.92));
  box-shadow: 0 24px 64px rgba(13, 42, 78, 0.18);
}

.dialog__header,
.dialog__footer {
  display: flex;
  justify-content: space-between;
  gap: 12px;
  align-items: center;
}

.dialog__footer {
  margin-top: 24px;
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

.field {
  display: grid;
  gap: 8px;
  margin-top: 18px;
  color: #274062;
}

.field span {
  font-size: 14px;
}

.field input {
  border: 1px solid rgba(70, 99, 140, 0.14);
  border-radius: 18px;
  padding: 14px 16px;
  font-size: 15px;
  background: rgba(255, 255, 255, 0.86);
}

.field input:focus {
  outline: none;
  border-color: rgba(61, 126, 255, 0.4);
  box-shadow: 0 0 0 4px rgba(61, 126, 255, 0.12);
}

.hint {
  margin: 16px 0 0;
  color: #607086;
  font-size: 13px;
  line-height: 1.6;
}

.error-text {
  margin: 14px 0 0;
  color: #a33b44;
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
</style>
