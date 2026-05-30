<script setup>
import { Position } from '@element-plus/icons-vue'
import MarkdownIt from 'markdown-it'
import { nextTick, ref } from 'vue'

import { sendChat } from '../api/chat'
import { buildApiUrl } from '../api/config'

const markdown = new MarkdownIt({
  breaks: true,
  html: false,
})

const input = ref('')
const deviceModel = ref('')
const loading = ref(false)
const messageListRef = ref(null)
const pagePreviewVisible = ref(false)
const pagePreviewUrl = ref('')
const pagePreviewTitle = ref('')
const messages = ref([
  {
    role: 'assistant',
    content: '你好，我是 AI 检修助手。请描述设备故障现象，我会结合知识库给出检修建议。',
    contexts: [],
  },
])

const scrollToBottom = async () => {
  await nextTick()
  const container = messageListRef.value
  if (container) {
    container.scrollTop = container.scrollHeight
  }
}

const renderMarkdown = (content) => {
  return markdown.render(String(content || ''))
}

const sleep = (delay) => {
  return new Promise((resolve) => {
    window.setTimeout(resolve, delay)
  })
}

const typeAnswer = async (message, answer) => {
  message.content = ''
  for (let index = 0; index < answer.length; index += 1) {
    message.content += answer[index]
    if (index % 12 === 0) {
      await scrollToBottom()
    }
    await sleep(8)
  }
  await scrollToBottom()
}

const sendMessage = async () => {
  const question = input.value.trim()
  if (!question || loading.value) return

  messages.value.push({
    role: 'user',
    content: question,
  })

  const pendingMessage = {
    role: 'assistant',
    content: 'AI正在分析设备故障...',
    contexts: [],
    retrievalFilter: {},
    graphContext: {},
    graphEnabled: false,
    graphWarnings: [],
    toolTrace: [],
    pending: true,
  }
  messages.value.push(pendingMessage)

  input.value = ''
  loading.value = true
  await scrollToBottom()

  try {
    const data = await sendChat(question, 5, deviceModel.value)
    const answer = data.answer || '未获取到有效回答'
    pendingMessage.contexts = Array.isArray(data.contexts) ? data.contexts : []
    pendingMessage.retrievalFilter = data.retrieval_filter || {}
    pendingMessage.graphContext = data.graph_context || {}
    pendingMessage.graphEnabled = Boolean(data.graph_enabled)
    pendingMessage.graphWarnings = data.graph_warnings || []
    pendingMessage.toolTrace = data.tool_trace || []
    await typeAnswer(pendingMessage, answer)
    pendingMessage.pending = false
  } catch (error) {
    pendingMessage.content = '后端服务连接失败'
    pendingMessage.contexts = []
    pendingMessage.retrievalFilter = {}
    pendingMessage.graphContext = {}
    pendingMessage.graphEnabled = false
    pendingMessage.graphWarnings = []
    pendingMessage.toolTrace = []
    pendingMessage.pending = false
  } finally {
    loading.value = false
    await scrollToBottom()
  }
}

const previewContent = (content) => {
  const text = String(content || '')
  return text.length > 200 ? `${text.slice(0, 200)}...` : text
}

const sourceLabel = (context) => (
  context?.source_type === 'feedback_case'
    ? '审核案例'
    : context?.source_type === 'manual_image'
      ? '手册图片'
      : '维修手册'
)
const getPagePreviewUrl = (context) => {
  const previewUrlValue = context?.preview_url || ''
  if (previewUrlValue.startsWith('http')) {
    return previewUrlValue
  }
  if (previewUrlValue.startsWith('/')) {
    return buildApiUrl(previewUrlValue)
  }
  if (context?.page_image_path) {
    return buildApiUrl(`/api/manual/page-image?path=${encodeURIComponent(context.page_image_path)}`)
  }
  return ''
}
const openPagePreview = (context) => {
  const url = getPagePreviewUrl(context)
  if (!url) return
  pagePreviewUrl.value = url
  pagePreviewTitle.value = `${context.pdf_filename || context.filename || '维修手册'} 第 ${context.page_number || context.page || '-'} 页`
  pagePreviewVisible.value = true
}

const graphPaths = (message) => message.graphContext?.paths || []
const toolStatusType = (status) => {
  if (status === 'success') return 'success'
  if (status === 'failed') return 'danger'
  return 'info'
}
</script>

<template>
  <section class="page chat-page">
    <div class="page-header">
      <div>
        <p class="eyebrow">AI Assistant</p>
        <h1>AI检修助手</h1>
      </div>
      <el-tag type="success">已接后端</el-tag>
    </div>

    <el-card shadow="never" class="chat-panel ai-chat-panel">
      <div ref="messageListRef" class="message-list ai-message-list">
        <div
          v-for="(message, index) in messages"
          :key="index"
          class="message-row"
          :class="message.role"
        >
          <div class="avatar">{{ message.role === 'assistant' ? 'AI' : '我' }}</div>

          <div class="message-stack">
            <el-card
              v-if="message.role === 'assistant'"
              shadow="never"
              class="assistant-card"
              :class="{ pending: message.pending }"
            >
              <div
                class="assistant-answer markdown-answer"
                v-html="renderMarkdown(message.content)"
              />

              <el-alert
                v-if="message.retrievalFilter?.filter_fallback"
                :title="message.retrievalFilter.filter_message"
                type="warning"
                :closable="false"
                show-icon
                class="filter-alert"
              />

              <div class="graph-context-section">
                <div class="context-title">关联图谱路径</div>
                <el-alert
                  v-if="!message.graphEnabled"
                  :title="message.graphWarnings?.[0] || '未匹配到关联图谱节点'"
                  type="info"
                  :closable="false"
                  show-icon
                />
                <div v-else class="graph-path-list">
                  <el-tag
                    v-for="seed in message.graphContext?.seed_nodes || []"
                    :key="seed.id"
                    type="warning"
                    effect="plain"
                  >
                    seed: {{ seed.name }}
                  </el-tag>
                  <div v-for="path in graphPaths(message)" :key="`${path.source}-${path.relation}-${path.target}`" class="graph-path-item">
                    <strong>{{ path.source }}</strong>
                    <el-tag size="small" type="primary">{{ path.relation }}</el-tag>
                    <strong>{{ path.target }}</strong>
                  </div>
                </div>
              </div>

              <el-collapse v-if="message.toolTrace?.length" class="tool-trace-collapse">
                <el-collapse-item title="工具链执行过程" :name="`trace-${index}`">
                  <div class="tool-trace-list">
                    <div v-for="tool in message.toolTrace" :key="tool.tool_name" class="tool-trace-item">
                      <div>
                        <strong>{{ tool.display_name }}</strong>
                        <p>{{ tool.output_summary }}</p>
                        <small v-if="tool.error">错误：{{ tool.error }}</small>
                      </div>
                      <div class="tool-trace-meta">
                        <el-tag :type="toolStatusType(tool.status)" effect="plain">{{ tool.status }}</el-tag>
                        <span>{{ tool.duration_ms || 0 }} ms</span>
                      </div>
                    </div>
                  </div>
                </el-collapse-item>
              </el-collapse>

              <div
                v-if="message.contexts && message.contexts.length > 0"
                class="context-section"
              >
                <div class="context-title">参考知识片段</div>
                <el-collapse>
                  <el-collapse-item
                    v-for="(context, contextIndex) in message.contexts"
                    :key="`${context.chunk_id || contextIndex}`"
                    :name="String(contextIndex)"
                  >
                    <template #title>
                      <span class="context-header">
                        {{ sourceLabel(context) }} · {{ context.filename || context.case_id || '未知来源' }} · 第 {{ context.page || '-' }} 页
                        <span v-if="context.device_model"> · 来源设备：{{ context.device_model }}</span>
                      </span>
                    </template>
                    <p class="context-content">
                      {{ previewContent(context.content) }}
                    </p>
                    <div class="context-actions">
                      <el-button
                        v-if="getPagePreviewUrl(context)"
                        size="small"
                        type="primary"
                        plain
                        @click="openPagePreview(context)"
                      >
                        查看原文页
                      </el-button>
                      <el-tag v-else-if="sourceLabel(context) === '审核案例'" type="success" effect="plain">
                        经验案例，无 PDF 页截图
                      </el-tag>
                    </div>
                  </el-collapse-item>
                </el-collapse>
              </div>
            </el-card>

            <div v-else class="message-bubble user-bubble">
              {{ message.content }}
            </div>
          </div>
        </div>
      </div>

      <div class="chat-input dark-chat-input">
        <el-input
          v-model="deviceModel"
          placeholder="设备型号，可选，例如 SINUMERIK 828D"
          :disabled="loading"
          clearable
        />
        <el-input
          v-model="input"
          type="textarea"
          :rows="3"
          resize="none"
          placeholder="请输入设备故障现象或检修问题"
          :disabled="loading"
          @keydown.enter.exact.prevent="sendMessage"
        />
        <el-button
          type="primary"
          :icon="Position"
          :loading="loading"
          :disabled="!input.trim()"
          @click="sendMessage"
        >
          发送
        </el-button>
      </div>
    </el-card>
    <el-dialog v-model="pagePreviewVisible" :title="pagePreviewTitle" width="72%">
      <img v-if="pagePreviewUrl" :src="pagePreviewUrl" class="page-preview-image" alt="维修手册原文页" />
    </el-dialog>
  </section>
</template>

<style scoped>
.ai-chat-panel {
  background: #f8fafc;
}

.ai-message-list {
  max-height: calc(100vh - 300px);
  min-height: 430px;
  padding: 8px;
}

.message-stack {
  min-width: 0;
  max-width: 100%;
}

.assistant-card {
  max-width: 760px;
  border: 1px solid #d4dce8;
  border-radius: 8px;
  background: #ffffff;
}

.assistant-card.pending {
  border-color: #93c5fd;
  background: #eff6ff;
}

.assistant-answer {
  color: #172033;
  line-height: 1.8;
}

.context-actions {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  margin-top: 10px;
}

.page-preview-image {
  width: 100%;
  max-height: 78vh;
  object-fit: contain;
  background: #f8fafc;
}

.filter-alert {
  margin: 12px 0;
}

.graph-context-section {
  margin-top: 14px;
}

.graph-path-list {
  display: grid;
  gap: 8px;
  padding: 10px;
  border: 1px solid #dbeafe;
  border-radius: 8px;
  background: #f8fafc;
}

.graph-path-item {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  align-items: center;
  color: #334155;
}

.tool-trace-collapse {
  margin-top: 12px;
}

.tool-trace-list {
  display: grid;
  gap: 8px;
}

.tool-trace-item {
  display: flex;
  justify-content: space-between;
  gap: 12px;
  padding: 10px;
  border: 1px solid #dbeafe;
  border-radius: 8px;
  background: #f8fafc;
}

.tool-trace-item p {
  margin: 4px 0;
  color: #475569;
}

.tool-trace-item small {
  color: #dc2626;
}

.tool-trace-meta {
  display: grid;
  justify-items: end;
  gap: 6px;
  color: #64748b;
  white-space: nowrap;
}

.markdown-answer :deep(h1),
.markdown-answer :deep(h2),
.markdown-answer :deep(h3),
.markdown-answer :deep(h4) {
  margin: 18px 0 10px;
  color: #0f172a;
  font-weight: 800;
  line-height: 1.35;
}

.markdown-answer :deep(h1) {
  padding-bottom: 8px;
  border-bottom: 1px solid #dbe2ea;
  font-size: 22px;
}

.markdown-answer :deep(h2) {
  font-size: 19px;
}

.markdown-answer :deep(h3) {
  font-size: 17px;
}

.markdown-answer :deep(h4) {
  font-size: 15px;
}

.markdown-answer :deep(p) {
  margin: 0 0 12px;
  color: #1f2937;
  line-height: 1.85;
}

.markdown-answer :deep(strong) {
  color: #111827;
  font-weight: 800;
}

.markdown-answer :deep(ul),
.markdown-answer :deep(ol) {
  margin: 8px 0 14px;
  padding-left: 24px;
}

.markdown-answer :deep(li) {
  margin: 6px 0;
  color: #1f2937;
  line-height: 1.75;
}

.markdown-answer :deep(hr) {
  height: 1px;
  margin: 18px 0;
  border: 0;
  background: #dbe2ea;
}

.markdown-answer :deep(code) {
  padding: 2px 6px;
  border-radius: 4px;
  background: #eef2f7;
  color: #1e3a8a;
  font-family: "SFMono-Regular", Consolas, "Liberation Mono", monospace;
  font-size: 0.92em;
}

.markdown-answer :deep(pre) {
  margin: 12px 0 16px;
  padding: 14px;
  overflow: auto;
  border: 1px solid #dbe2ea;
  border-radius: 8px;
  background: #f1f5f9;
}

.markdown-answer :deep(pre code) {
  display: block;
  padding: 0;
  background: transparent;
  color: #172033;
  line-height: 1.7;
  white-space: pre;
}

.markdown-answer :deep(blockquote) {
  margin: 12px 0;
  padding: 10px 14px;
  border-left: 4px solid #2563eb;
  background: #f8fafc;
  color: #334155;
}

.markdown-answer :deep(:first-child) {
  margin-top: 0;
}

.markdown-answer :deep(:last-child) {
  margin-bottom: 0;
}

.user-bubble {
  max-width: 680px;
  background: #1d4ed8;
  border-color: #1d4ed8;
  color: #ffffff;
  white-space: pre-wrap;
}

.context-section {
  margin-top: 14px;
  padding-top: 12px;
  border-top: 1px solid #e5e7eb;
}

.context-title {
  margin-bottom: 8px;
  color: #334155;
  font-size: 13px;
  font-weight: 800;
}

.context-header {
  color: #1f2937;
  font-size: 13px;
  font-weight: 700;
}

.context-content {
  margin: 0;
  color: #5f6b7a;
  line-height: 1.7;
}

.dark-chat-input {
  margin: 0 -4px -4px;
  padding: 16px;
  background: #111827;
  border: 1px solid #263244;
  border-radius: 8px;
}

.dark-chat-input :deep(.el-textarea__inner) {
  background: #0f172a;
  border-color: #334155;
  color: #e5e7eb;
  box-shadow: none;
}

.dark-chat-input :deep(.el-textarea__inner::placeholder) {
  color: #7f8da3;
}
</style>
