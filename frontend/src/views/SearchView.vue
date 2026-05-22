<script setup>
import { Document, Search } from '@element-plus/icons-vue'
import { ElMessage } from 'element-plus'
import { ref } from 'vue'

import { semanticSearch } from '../api/manual'

const keyword = ref('')
const topK = ref(5)
const loading = ref(false)
const hasSearched = ref(false)
const results = ref([])
const expandedIds = ref(new Set())

const handleSearch = async () => {
  const query = keyword.value.trim()
  if (!query) {
    ElMessage.warning('请输入搜索关键词')
    return
  }

  loading.value = true
  hasSearched.value = true
  expandedIds.value = new Set()

  try {
    const data = await semanticSearch(query, topK.value)
    results.value = Array.isArray(data.results) ? data.results : []
  } catch (error) {
    results.value = []
    ElMessage.error('语义检索失败，请检查后端服务')
  } finally {
    loading.value = false
  }
}

const getResultKey = (item, index) => {
  return item.chunk_id || `${item.filename || 'manual'}-${item.page || 0}-${index}`
}

const isExpanded = (key) => {
  return expandedIds.value.has(key)
}

const toggleExpanded = (key) => {
  const next = new Set(expandedIds.value)
  if (next.has(key)) {
    next.delete(key)
  } else {
    next.add(key)
  }
  expandedIds.value = next
}

const getContent = (item, key) => {
  const content = String(item.content || '')
  if (content.length <= 300 || isExpanded(key)) {
    return content
  }

  return `${content.slice(0, 300)}...`
}

const formatScore = (score) => {
  if (typeof score !== 'number') {
    return '-'
  }

  return score.toFixed(4)
}
</script>

<template>
  <section class="page">
    <div class="page-header">
      <div>
        <p class="eyebrow">Semantic Search</p>
        <h1>知识检索</h1>
      </div>
      <el-tag type="success">语义检索</el-tag>
    </div>

    <el-card shadow="never" class="search-panel semantic-search-panel">
      <div class="search-toolbar">
        <el-input
          v-model="keyword"
          size="large"
          placeholder="输入设备名称、故障现象或检修关键词"
          clearable
          @keydown.enter="handleSearch"
        />
        <el-input-number
          v-model="topK"
          size="large"
          :min="1"
          :max="20"
          controls-position="right"
        />
        <el-button
          type="primary"
          color="#111827"
          size="large"
          :icon="Search"
          :loading="loading"
          @click="handleSearch"
        >
          搜索
        </el-button>
      </div>

      <div class="search-hint">
        <span>返回数量：{{ topK }}</span>
        <span>接口：/api/manual/semantic-search</span>
      </div>

      <div v-loading="loading" class="semantic-result-area">
        <el-empty
          v-if="hasSearched && !results.length && !loading"
          description="未检索到相关知识片段"
          :image-size="96"
        />
        <el-empty
          v-else-if="!hasSearched && !results.length"
          description="输入关键词后开始检索知识库"
          :image-size="96"
        />

        <div v-else class="result-list">
          <div
            v-for="(item, index) in results"
            :key="getResultKey(item, index)"
            class="result-card semantic-result-card"
          >
            <div class="result-card-head">
              <div class="result-file">
                <span class="file-icon">
                  <el-icon><Document /></el-icon>
                </span>
                <div>
                  <div class="result-title">{{ item.filename || '未知文件' }}</div>
                  <div class="result-meta">
                    第 {{ item.page || '-' }} 页 · chunk_id: {{ item.chunk_id || '-' }}
                  </div>
                </div>
              </div>
              <el-tag type="info">score {{ formatScore(item.score) }}</el-tag>
            </div>

            <p class="result-content">
              {{ getContent(item, getResultKey(item, index)) }}
            </p>

            <el-button
              v-if="String(item.content || '').length > 300"
              link
              type="primary"
              @click="toggleExpanded(getResultKey(item, index))"
            >
              {{ isExpanded(getResultKey(item, index)) ? '收起全文' : '展开全文' }}
            </el-button>
          </div>
        </div>
      </div>
    </el-card>
  </section>
</template>

<style scoped>
.semantic-search-panel {
  min-height: 620px;
}

.search-toolbar {
  display: grid;
  grid-template-columns: minmax(0, 1fr) 140px 112px;
  gap: 12px;
}

.search-hint {
  display: flex;
  justify-content: space-between;
  gap: 12px;
  padding: 10px 12px;
  border: 1px solid #dbe2ea;
  border-radius: 8px;
  background: #f8fafc;
  color: #64748b;
  font-size: 13px;
}

.semantic-result-area {
  min-height: 420px;
}

.semantic-result-card {
  background: #ffffff;
}

.result-card-head {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 14px;
}

.result-file {
  display: flex;
  min-width: 0;
  gap: 12px;
}

.file-icon {
  display: flex;
  width: 38px;
  height: 38px;
  flex: 0 0 38px;
  align-items: center;
  justify-content: center;
  border-radius: 8px;
  background: #111827;
  color: #ffffff;
}

.result-content {
  margin: 14px 0 0;
  color: #334155;
  line-height: 1.8;
  white-space: pre-wrap;
}

@media (max-width: 900px) {
  .search-toolbar {
    grid-template-columns: 1fr;
  }

  .result-card-head {
    flex-direction: column;
  }
}
</style>
