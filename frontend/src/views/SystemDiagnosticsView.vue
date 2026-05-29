<script setup>
import { ElMessage, ElMessageBox } from 'element-plus'
import { computed, onMounted, ref } from 'vue'

import { getSystemDiagnostics } from '../api/diagnostics'
import { useAuthStore } from '../stores/auth'

const auth = useAuthStore()
const diagnostics = ref(null)
const loading = ref(false)
const errorMessage = ref('')

const modules = computed(() => diagnostics.value?.modules || [])
const checklist = computed(() => diagnostics.value?.demo_checklist || [])
const overallStatus = computed(() => diagnostics.value?.overall_status || 'warning')

const statusType = (status) => {
  if (status === 'ok') return 'success'
  if (status === 'error') return 'danger'
  return 'warning'
}

const statusText = (status) => {
  if (status === 'ok') return '正常'
  if (status === 'error') return '异常'
  return '警告'
}

const formatMetricValue = (value) => {
  if (Array.isArray(value)) return value.join(' / ')
  if (value && typeof value === 'object') {
    return Object.entries(value)
      .map(([key, item]) => `${key}: ${item}`)
      .join('；')
  }
  if (typeof value === 'boolean') return value ? '是' : '否'
  return value ?? '-'
}

const loadDiagnostics = async (deepCheck = false) => {
  loading.value = true
  errorMessage.value = ''
  try {
    diagnostics.value = await getSystemDiagnostics(deepCheck)
    ElMessage.success(deepCheck ? '深度诊断完成' : '系统诊断已刷新')
  } catch (error) {
    errorMessage.value = error?.response?.data?.detail || '系统诊断接口连接失败'
    ElMessage.error(errorMessage.value)
  } finally {
    loading.value = false
  }
}

const runDeepCheck = async () => {
  try {
    await ElMessageBox.confirm(
      '深度检查会进行一次轻量模型连通性测试，可能产生少量模型调用费用。是否继续？',
      '确认执行深度检查',
      {
        confirmButtonText: '继续检查',
        cancelButtonText: '取消',
        type: 'warning',
      },
    )
    await loadDiagnostics(true)
  } catch (error) {
    if (error !== 'cancel') {
      ElMessage.info('已取消深度检查')
    }
  }
}

onMounted(() => loadDiagnostics(false))
</script>

<template>
  <section class="page diagnostics-page">
    <div class="diagnostics-hero">
      <div>
        <p class="eyebrow">System Diagnostics</p>
        <h1>系统诊断</h1>
        <p>快速检查 RAG、Chroma、手册截图、知识图谱、Lazy GraphRAG、工具链和模型配置状态。</p>
      </div>
      <div class="hero-actions">
        <el-tag type="danger" effect="dark">仅系统管理员</el-tag>
        <el-button :loading="loading" @click="loadDiagnostics(false)">一键刷新</el-button>
        <el-button type="warning" :loading="loading" @click="runDeepCheck">深度检查</el-button>
      </div>
    </div>

    <el-alert
      v-if="errorMessage"
      :title="errorMessage"
      type="error"
      show-icon
      :closable="false"
      class="status-alert"
    />

    <div v-loading="loading" class="diagnostics-body">
      <div class="overview-grid">
        <el-card shadow="never" class="overview-card">
          <span>总体状态</span>
          <strong>{{ statusText(overallStatus) }}</strong>
          <el-tag :type="statusType(overallStatus)" effect="dark">{{ overallStatus }}</el-tag>
        </el-card>
        <el-card shadow="never" class="overview-card">
          <span>检查时间</span>
          <strong>{{ diagnostics?.checked_at || '-' }}</strong>
          <el-tag type="info">实时自检</el-tag>
        </el-card>
        <el-card shadow="never" class="overview-card">
          <span>当前角色</span>
          <strong>{{ auth.display_name || '系统管理员' }}</strong>
          <el-tag type="primary">{{ auth.role || 'admin' }}</el-tag>
        </el-card>
        <el-card shadow="never" class="overview-card">
          <span>深度检查</span>
          <strong>{{ diagnostics?.deep_check ? '已执行' : '未执行' }}</strong>
          <el-tag :type="diagnostics?.deep_check ? 'warning' : 'info'">LLM 连通性</el-tag>
        </el-card>
      </div>

      <el-card shadow="never" class="checklist-card">
        <template #header>
          <div class="card-title">
            <span>演示检查清单</span>
            <el-tag type="info">Demo Readiness</el-tag>
          </div>
        </template>
        <div v-if="checklist.length" class="checklist-grid">
          <div v-for="item in checklist" :key="item.name" class="check-item">
            <el-tag :type="statusType(item.status)" effect="dark">{{ statusText(item.status) }}</el-tag>
            <div>
              <strong>{{ item.name }}</strong>
              <p>{{ item.message }}</p>
            </div>
          </div>
        </div>
        <el-empty v-else description="暂无检查结果" />
      </el-card>

      <div class="module-grid">
        <el-card v-for="module in modules" :key="module.name" shadow="never" class="module-card">
          <template #header>
            <div class="card-title">
              <span>{{ module.name }}</span>
              <el-tag :type="statusType(module.status)" effect="dark">{{ statusText(module.status) }}</el-tag>
            </div>
          </template>
          <p class="module-message">{{ module.message }}</p>

          <div v-if="Object.keys(module.metrics || {}).length" class="metric-list">
            <div v-for="(value, key) in module.metrics" :key="key" class="metric-row">
              <span>{{ key }}</span>
              <strong>{{ formatMetricValue(value) }}</strong>
            </div>
          </div>

          <div v-if="module.warnings?.length" class="warning-list">
            <el-alert
              v-for="warning in module.warnings"
              :key="warning"
              :title="warning"
              type="warning"
              show-icon
              :closable="false"
            />
          </div>
        </el-card>
      </div>
    </div>
  </section>
</template>

<style scoped>
.diagnostics-page {
  display: flex;
  flex-direction: column;
  gap: 18px;
}

.diagnostics-hero {
  display: flex;
  justify-content: space-between;
  gap: 18px;
  padding: 24px;
  border: 1px solid #1e3a5f;
  border-radius: 10px;
  background: linear-gradient(135deg, #0f172a, #13233a);
  color: #fff;
}

.diagnostics-hero h1 {
  margin: 6px 0 8px;
  font-size: 30px;
  letter-spacing: 0;
}

.diagnostics-hero p:last-child {
  margin: 0;
  color: #b7c4d7;
}

.hero-actions {
  display: flex;
  align-items: flex-start;
  gap: 10px;
  flex-wrap: wrap;
  justify-content: flex-end;
}

.status-alert {
  border-radius: 8px;
}

.diagnostics-body {
  display: flex;
  flex-direction: column;
  gap: 16px;
}

.overview-grid {
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: 14px;
}

.overview-card,
.checklist-card,
.module-card {
  border: 1px solid #dbe2ea;
  border-radius: 10px;
}

.overview-card span {
  color: #64748b;
  font-weight: 700;
}

.overview-card strong {
  display: block;
  min-height: 30px;
  margin: 8px 0;
  color: #111827;
  font-size: 20px;
}

.card-title {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  font-weight: 800;
  color: #111827;
}

.checklist-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 12px;
}

.check-item {
  display: flex;
  gap: 12px;
  align-items: flex-start;
  padding: 12px;
  border: 1px solid #dbeafe;
  border-radius: 8px;
  background: #f8fafc;
}

.check-item strong {
  display: block;
  color: #111827;
}

.check-item p {
  margin: 4px 0 0;
  color: #64748b;
  line-height: 1.6;
}

.module-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 16px;
}

.module-message {
  margin: 0 0 12px;
  color: #334155;
  line-height: 1.7;
}

.metric-list {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.metric-row {
  display: grid;
  grid-template-columns: minmax(140px, 0.35fr) minmax(0, 1fr);
  gap: 10px;
  padding: 8px 10px;
  border-radius: 8px;
  background: #f1f5f9;
  color: #475569;
}

.metric-row span {
  font-family: Consolas, monospace;
  font-size: 12px;
  word-break: break-all;
}

.metric-row strong {
  color: #0f172a;
  font-size: 13px;
  word-break: break-word;
}

.warning-list {
  display: flex;
  flex-direction: column;
  gap: 8px;
  margin-top: 12px;
}

@media (max-width: 1100px) {
  .overview-grid,
  .module-grid,
  .checklist-grid {
    grid-template-columns: 1fr;
  }

  .diagnostics-hero {
    flex-direction: column;
  }

  .hero-actions {
    justify-content: flex-start;
  }
}
</style>
