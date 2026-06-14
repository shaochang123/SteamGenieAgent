<template>
  <form class="composer" @submit.prevent="submit">
    <textarea
      v-model.trim="draft"
      class="composer__input"
      :disabled="disabled"
      rows="1"
      placeholder="给 AI 发送一条消息..."
      @keydown.enter.exact.prevent="submit"
    ></textarea>

    <button class="composer__button" type="submit" :disabled="disabled || !draft">
      {{ loading ? '发送中...' : '发送' }}
    </button>
  </form>
</template>

<script>
export default {
  name: 'ChatComposer',
  props: {
    loading: {
      type: Boolean,
      default: false,
    },
    disabled: {
      type: Boolean,
      default: false,
    },
  },
  data() {
    return {
      draft: '',
    }
  },
  methods: {
    submit() {
      if (!this.draft || this.disabled) {
        return
      }
      this.$emit('send', this.draft)
      this.draft = ''
    },
  },
}
</script>

<style lang="less" scoped>
.composer {
  display: grid;
  grid-template-columns: minmax(0, 1fr) auto;
  gap: 12px;
  align-items: end;
  padding: 16px;
  border-radius: 28px;
  background: rgba(255, 255, 255, 0.8);
  box-shadow: inset 0 1px 0 rgba(255, 255, 255, 0.65), 0 16px 30px rgba(17, 45, 79, 0.08);
  position: sticky;
  bottom: 0;
  z-index: 2;
  margin-top: auto;
}

.composer__input {
  resize: none;
  min-height: 52px;
  max-height: 148px;
  border: 0;
  border-radius: 20px;
  padding: 14px 16px;
  background: rgba(242, 247, 255, 0.92);
  font: inherit;
  color: #102542;
}

.composer__input:focus {
  outline: none;
  box-shadow: 0 0 0 4px rgba(61, 126, 255, 0.12);
}

.composer__button {
  border: 0;
  border-radius: 18px;
  min-width: 108px;
  height: 52px;
  padding: 0 18px;
  background: linear-gradient(135deg, #3d7eff, #5b8cff);
  color: #fff;
  font-weight: 600;
  cursor: pointer;
  box-shadow: 0 18px 28px rgba(61, 126, 255, 0.24);
}

.composer__button:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

@media (max-width: 720px) {
  .composer {
    grid-template-columns: 1fr;
  }

  .composer__button {
    width: 100%;
  }
}
</style>
