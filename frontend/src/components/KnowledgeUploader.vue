<template>
  <div class="knowledge-section">
    <div class="knowledge-header" @click="expanded = !expanded">
      <span class="knowledge-title">知识库</span>
      <span class="knowledge-toggle">{{ expanded ? '收起' : '展开' }}</span>
    </div>

    <div v-if="expanded" class="knowledge-body">
      <div
        class="knowledge-drop-zone"
        @dragover.prevent
        @dragenter.prevent="dragOver = true"
        @dragleave.prevent="dragOver = false"
        @drop.prevent="handleDrop"
        @click="$refs.fileInput.click()"
        :class="{ 'drop-active': dragOver }"
      >
        <p>拖拽 JSON 文件到此，或点击选择文件</p>
        <input
          type="file"
          accept=".json"
          hidden
          ref="fileInput"
          @change="handleFileSelect"
        >
      </div>

      <p v-if="uploading" class="upload-status">上传中...</p>
      <p v-if="uploadError" class="upload-error">{{ uploadError }}</p>

      <div v-if="allFiles.length" class="knowledge-list">
        <div
          v-for="file in allFiles"
          :key="file.source + file.name"
          class="knowledge-item"
        >
          <span class="knowledge-item__name">{{ file.name }}</span>
          <span class="knowledge-item__tag" :class="file.source === 'public' ? 'tag--public' : 'tag--user'">
            {{ file.source === 'public' ? '公共' : '用户' }}
          </span>
          <button
            v-if="file.source === 'user'"
            class="knowledge-item__delete"
            @click="handleDelete(file.name)"
          >
            删除
          </button>
        </div>
      </div>

      <p v-else class="knowledge-empty">暂无知识文件</p>
    </div>
  </div>
</template>

<script>
import { getKnowledge, uploadKnowledge, deleteKnowledge } from '../api/api'

export default {
  name: 'KnowledgeUploader',
  props: {
    profileId: {
      type: String,
      default: '',
    },
  },
  data() {
    return {
      expanded: false,
      dragOver: false,
      uploading: false,
      uploadError: '',
      files: { public: [], user: [] },
    }
  },
  computed: {
    allFiles() {
      return [...this.files.public, ...this.files.user]
    },
  },
  watch: {
    profileId: {
      immediate: true,
      handler(val) {
        if (val) {
          this.loadFiles()
        }
      },
    },
  },
  methods: {
    async loadFiles() {
      try {
        const response = await getKnowledge(this.profileId)
        this.files = response.data || { public: [], user: [] }
      } catch {
        this.files = { public: [], user: [] }
      }
    },
    async handleDrop(e) {
      this.dragOver = false
      const files = e.dataTransfer?.files || []
      for (const file of files) {
        await this.uploadFile(file)
      }
    },
    async handleFileSelect(e) {
      const files = e.target.files || []
      for (const file of files) {
        await this.uploadFile(file)
      }
      if (this.$refs.fileInput) {
        this.$refs.fileInput.value = ''
      }
    },
    async uploadFile(file) {
      if (!file.name.toLowerCase().endsWith('.json')) {
        this.uploadError = '仅支持 .json 文件'
        return
      }
      this.uploading = true
      this.uploadError = ''
      try {
        await uploadKnowledge(this.profileId, file)
        await this.loadFiles()
      } catch (error) {
        this.uploadError = error?.response?.data?.detail || error.message || '上传失败'
      } finally {
        this.uploading = false
      }
    },
    async handleDelete(filename) {
      try {
        await deleteKnowledge(this.profileId, filename)
        await this.loadFiles()
      } catch (error) {
        this.uploadError = error?.response?.data?.detail || error.message || '删除失败'
      }
    },
  },
}
</script>

<style lang="less" scoped>
.knowledge-section {
  border-radius: 18px;
  background: rgba(255, 255, 255, 0.64);
  padding: 12px 16px;
  flex: 0 0 auto;
}

.knowledge-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  cursor: pointer;
}

.knowledge-title {
  font-size: 14px;
  font-weight: 600;
  color: #102542;
}

.knowledge-toggle {
  font-size: 12px;
  color: #607086;
}

.knowledge-body {
  margin-top: 12px;
  display: flex;
  flex-direction: column;
  gap: 10px;
}

.knowledge-drop-zone {
  border: 2px dashed rgba(70, 99, 140, 0.2);
  border-radius: 14px;
  padding: 18px;
  text-align: center;
  cursor: pointer;
  transition: border-color 0.15s;
}

.knowledge-drop-zone p {
  margin: 0;
  color: #607086;
  font-size: 13px;
}

.knowledge-drop-zone.drop-active {
  border-color: rgba(61, 126, 255, 0.5);
  background: rgba(61, 126, 255, 0.06);
}

.upload-status {
  margin: 0;
  font-size: 13px;
  color: #3d7eff;
}

.upload-error {
  margin: 0;
  font-size: 13px;
  color: #a33b44;
}

.knowledge-list {
  display: flex;
  flex-direction: column;
  gap: 6px;
  max-height: 160px;
  overflow: auto;
}

.knowledge-item {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 13px;
}

.knowledge-item__name {
  flex: 1;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  color: #102542;
}

.knowledge-item__tag {
  font-size: 10px;
  padding: 2px 8px;
  border-radius: 8px;
}

.tag--public {
  background: rgba(61, 126, 255, 0.12);
  color: #3d7eff;
}

.tag--user {
  background: rgba(82, 196, 127, 0.12);
  color: #34a853;
}

.knowledge-item__delete {
  border: 0;
  border-radius: 8px;
  padding: 2px 10px;
  background: rgba(255, 120, 120, 0.12);
  color: #a33b44;
  cursor: pointer;
  font-size: 12px;
}

.knowledge-empty {
  margin: 0;
  font-size: 13px;
  color: #8a99ae;
  text-align: center;
}
</style>
