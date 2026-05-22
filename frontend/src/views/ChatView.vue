<script setup>
import { Position } from '@element-plus/icons-vue'
import { nextTick, ref } from 'vue'

import { sendChat } from '../api/chat'

const input = ref('')
const loading = ref(false)
const messageListRef = ref(null)
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
    pending: true,
  }
  messages.value.push(pendingMessage)

  input.value = ''
  loading.value = true
  await scrollToBottom()

  try {
    const data = await sendChat(question, 5)
    pendingMessage.content = data.answer || '未获取到有效回答'
    pendingMessage.contexts = Array.isArray(data.contexts) ? data.contexts : []
    pendingMessage.pending = false
  } catch (error) {
    pendingMessage.content = '后端服务连接失败'
    pendingMessage.contexts = []
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
              <div class="assistant-answer">{{ message.content }}</div>

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
                        {{ context.filename || '未知文件' }} · 第 {{ context.page || '-' }} 页
                      </span>
                    </template>
                    <p class="context-content">
                      {{ previewContent(context.content) }}
                    </p>
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
  white-space: pre-wrap;
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
