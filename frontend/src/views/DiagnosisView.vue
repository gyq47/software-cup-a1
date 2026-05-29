<script setup>
import { Camera, DocumentChecked, UploadFilled, WarningFilled } from '@element-plus/icons-vue'
import { ElMessage } from 'element-plus'
import { computed, ref } from 'vue'
import { useRouter } from 'vue-router'

import { diagnoseImage } from '../api/diagnosis'

const router = useRouter()
const imageFile = ref(null)
const previewUrl = ref('')
const text = ref('')
const deviceModel = ref('')
const loading = ref(false)
const result = ref(null)

const vision = computed(() => result.value?.vision_result || {})
const diagnosis = computed(() => result.value?.diagnosis || {})
const contexts = computed(() => result.value?.contexts || [])
const evidenceItems = computed(() => result.value?.evidence_items || [])
const generatedQuery = computed(() => diagnosis.value.generated_query || '')

const beforeImageUpload = (file) => {
  if (!file.type.startsWith('image/')) {
    ElMessage.error('请上传图片文件')
    return false
  }
  imageFile.value = file
  previewUrl.value = URL.createObjectURL(file)
  result.value = null
  return false
}

const startDiagnosis = async () => {
  if (!imageFile.value) {
    ElMessage.warning('请先上传故障图片')
    return
  }

  loading.value = true
  try {
    result.value = await diagnoseImage({
      image: imageFile.value,
      text: text.value.trim(),
      deviceModel: deviceModel.value.trim(),
    })
    ElMessage.success('故障诊断已完成')
  } catch (error) {
    result.value = null
    ElMessage.error('多模态故障诊断失败，请检查后端服务')
  } finally {
    loading.value = false
  }
}

const goWorkflow = () => {
  router.push({
    path: '/workflow',
    query: {
      task: generatedQuery.value || text.value || vision.value.analysis_text || '设备故障检修',
    },
  })
}

const goFeedback = () => {
  router.push({
    path: '/feedback',
    query: {
      source_type: 'diagnosis',
      question: generatedQuery.value || text.value || '设备故障诊断',
    },
  })
}

const riskType = (level) => {
  if (level === 'high') return 'danger'
  if (level === 'medium') return 'warning'
  return 'success'
}

const formatScore = (score) => {
  const value = Number(score)
  if (!Number.isFinite(value)) return '-'
  return value.toFixed(2)
}
</script>

<template>
  <section class="page diagnosis-page">
    <div class="diagnosis-hero">
      <div>
        <p class="eyebrow">Multimodal Diagnosis</p>
        <h1>多模态故障诊断</h1>
        <p>上传设备故障图片，自动识别现象并联动知识库生成检修建议。</p>
      </div>
      <el-tag type="primary" effect="dark">Qwen-VL · Hybrid Search</el-tag>
    </div>

    <el-card shadow="never" class="diagnosis-input-card">
      <div class="diagnosis-input-grid">
        <el-upload
          drag
          action="#"
          :auto-upload="false"
          :show-file-list="false"
          accept="image/*"
          :before-upload="beforeImageUpload"
        >
          <el-icon class="el-icon--upload"><UploadFilled /></el-icon>
          <div class="el-upload__text">拖拽故障图片到此处，或 <em>点击选择</em></div>
        </el-upload>

        <div class="diagnosis-form">
          <el-input v-model="deviceModel" size="large" placeholder="设备型号，可选" />
          <el-input
            v-model="text"
            type="textarea"
            :rows="4"
            resize="none"
            placeholder="补充现场现象，例如：发动机无法启动，仪表显示 E201"
          />
          <el-button
            type="primary"
            color="#111827"
            size="large"
            :icon="Camera"
            :loading="loading"
            @click="startDiagnosis"
          >
            开始诊断
          </el-button>
        </div>
      </div>
    </el-card>

    <el-skeleton v-if="loading" :rows="8" animated class="diagnosis-skeleton" />

    <el-empty
      v-else-if="!result"
      description="上传故障图片后开始诊断"
      :image-size="120"
    />

    <div v-else class="diagnosis-result-grid">
      <el-card shadow="never" class="image-preview-card">
        <template #header>
          <div class="card-header">图片预览</div>
        </template>
        <img v-if="previewUrl" :src="previewUrl" alt="故障图片预览" class="preview-image" />
      </el-card>

      <el-card shadow="never" class="diagnosis-card">
        <template #header>
          <div class="card-header">
            <span>识别结果</span>
            <el-tag :type="riskType(vision.risk_level)" effect="dark">
              {{ vision.risk_level || 'medium' }}
            </el-tag>
          </div>
        </template>
        <p class="diagnosis-summary">{{ vision.analysis_text }}</p>
        <div class="tag-section">
          <span>识别零件</span>
          <el-tag v-for="item in vision.visible_parts" :key="item" effect="plain">{{ item }}</el-tag>
        </div>
        <div class="tag-section">
          <span>故障代码</span>
          <el-tag v-for="item in vision.fault_codes" :key="item" type="warning" effect="plain">{{ item }}</el-tag>
          <el-tag v-if="!vision.fault_codes?.length" type="info" effect="plain">未识别</el-tag>
        </div>
        <div class="query-box">
          <strong>自动生成 query</strong>
          <p>{{ generatedQuery || '-' }}</p>
        </div>
      </el-card>

      <el-card shadow="never" class="diagnosis-report-card">
        <template #header>
          <div class="card-header">
            <span>工业诊断结果</span>
            <el-tag type="info">{{ contexts.length }} 个知识片段</el-tag>
          </div>
        </template>

        <el-alert
          :title="diagnosis.summary"
          type="info"
          :closable="false"
          show-icon
          class="report-alert"
        />

        <div class="report-columns">
          <div class="report-block">
            <h3>故障分析</h3>
            <p v-for="item in diagnosis.fault_analysis" :key="item">{{ item }}</p>
          </div>
          <div class="report-block">
            <h3>检查步骤</h3>
            <p v-for="item in diagnosis.inspection_steps" :key="item">{{ item }}</p>
          </div>
          <div class="report-block">
            <h3>维修建议</h3>
            <p v-for="item in diagnosis.repair_suggestions" :key="item">{{ item }}</p>
          </div>
          <div class="report-block safety">
            <h3><el-icon><WarningFilled /></el-icon> 安全提醒</h3>
            <p v-for="item in diagnosis.safety_notices" :key="item">{{ item }}</p>
          </div>
        </div>

        <div class="diagnosis-evidence-panel">
          <div class="evidence-panel-head">
            <div>
              <h3>诊断依据</h3>
              <p>AI 诊断结果基于维修手册命中片段生成，建议结合原手册页码和图示复核。</p>
            </div>
            <el-tag type="primary">{{ evidenceItems.length }} 条依据</el-tag>
          </div>

          <el-empty
            v-if="!evidenceItems.length"
            description="暂无手册依据"
            :image-size="90"
          />

          <el-collapse v-else class="diagnosis-evidence-collapse">
            <el-collapse-item
              v-for="(item, index) in evidenceItems"
              :key="item.chunk_id || `${item.filename}-${item.page}-${index}`"
              :name="`diagnosis-evidence-${index}`"
            >
              <template #title>
                <div class="diagnosis-evidence-title">
                  <span>{{ item.filename || '未知手册' }}</span>
                  <el-tag type="primary" effect="dark">第 {{ item.page || '-' }} 页</el-tag>
                </div>
              </template>

              <div class="diagnosis-evidence-item">
                <p class="evidence-summary">{{ item.summary }}</p>
                <div class="evidence-score-row">
                  <el-tag type="success" effect="plain">
                    final {{ formatScore(item.final_score) }}
                  </el-tag>
                  <el-tag type="warning" effect="plain">
                    bm25 {{ formatScore(item.bm25_score) }}
                  </el-tag>
                  <el-tag type="info" effect="plain">
                    hits {{ item.keyword_hits || 0 }}
                  </el-tag>
                </div>
                <div class="evidence-chunk-id">chunk_id: {{ item.chunk_id || '-' }}</div>
                <p class="evidence-raw-text">{{ item.content }}</p>
                <el-alert
                  v-if="!item.preview_available"
                  title="暂未生成页面预览，可根据文件名和页码定位原始手册。"
                  type="info"
                  :closable="false"
                  show-icon
                />
              </div>
            </el-collapse-item>
          </el-collapse>
        </div>

        <div class="workflow-entry">
          <el-button @click="goFeedback">
            提交诊断修正
          </el-button>
          <el-button
            type="primary"
            color="#111827"
            :icon="DocumentChecked"
            :disabled="!diagnosis.workflow_recommended"
            @click="goWorkflow"
          >
            基于该依据生成标准作业卡
          </el-button>
        </div>
      </el-card>
    </div>
  </section>
</template>

<style scoped>
.diagnosis-page {
  gap: 18px;
}

.diagnosis-hero {
  display: flex;
  justify-content: space-between;
  gap: 18px;
  padding: 22px 24px;
  border: 1px solid #1f2a3a;
  border-radius: 10px;
  background: #111827;
  color: #ffffff;
}

.diagnosis-hero h1 {
  margin: 6px 0 8px;
  font-size: 30px;
}

.diagnosis-hero p:last-child {
  margin: 0;
  color: #aeb8c8;
}

.diagnosis-input-card,
.image-preview-card,
.diagnosis-card,
.diagnosis-report-card {
  border: 1px solid #dbe2ea;
  border-radius: 10px;
  box-shadow: 0 8px 22px rgba(15, 23, 42, 0.08);
}

.diagnosis-input-grid {
  display: grid;
  grid-template-columns: minmax(320px, 0.8fr) minmax(0, 1fr);
  gap: 18px;
}

.diagnosis-form {
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.diagnosis-skeleton {
  padding: 20px;
  border-radius: 10px;
  background: #ffffff;
}

.diagnosis-result-grid {
  display: grid;
  grid-template-columns: minmax(320px, 0.85fr) minmax(0, 1.15fr);
  gap: 18px;
}

.diagnosis-report-card {
  grid-column: 1 / -1;
}

.card-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  font-weight: 800;
}

.preview-image {
  display: block;
  width: 100%;
  max-height: 420px;
  object-fit: contain;
  border-radius: 8px;
  background: #0f172a;
}

.diagnosis-summary,
.query-box p {
  color: #334155;
  line-height: 1.8;
}

.tag-section {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  margin-top: 14px;
}

.tag-section span {
  width: 72px;
  color: #64748b;
  font-weight: 800;
}

.query-box {
  margin-top: 16px;
  padding: 12px;
  border: 1px solid #dbe2ea;
  border-radius: 8px;
  background: #f8fafc;
}

.report-alert {
  margin-bottom: 16px;
}

.report-columns {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 14px;
}

.report-block {
  padding: 16px;
  border: 1px solid #dbe2ea;
  border-radius: 8px;
  background: #f8fafc;
}

.report-block.safety {
  border-color: #fecaca;
  background: #fff7f7;
}

.report-block h3 {
  display: flex;
  align-items: center;
  gap: 6px;
  margin: 0 0 10px;
  color: #111827;
}

.report-block p {
  margin: 8px 0 0;
  color: #334155;
  line-height: 1.75;
}

.workflow-entry {
  display: flex;
  justify-content: flex-end;
  gap: 10px;
  margin-top: 16px;
}

.diagnosis-evidence-panel {
  margin-top: 16px;
  padding: 16px;
  border: 1px solid #bfdbfe;
  border-radius: 10px;
  background: #f8fafc;
}

.evidence-panel-head {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 14px;
  margin-bottom: 12px;
}

.evidence-panel-head h3 {
  margin: 0 0 6px;
  color: #111827;
}

.evidence-panel-head p {
  margin: 0;
  color: #64748b;
  line-height: 1.7;
}

.diagnosis-evidence-collapse {
  border-top: 1px solid #dbeafe;
}

.diagnosis-evidence-title {
  display: flex;
  min-width: 0;
  flex: 1;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
  padding-right: 8px;
}

.diagnosis-evidence-title span {
  overflow: hidden;
  color: #172033;
  font-weight: 800;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.diagnosis-evidence-item {
  padding: 12px;
  border: 1px solid #dbeafe;
  border-radius: 8px;
  background: #ffffff;
}

.evidence-summary,
.evidence-raw-text {
  margin: 0 0 10px;
  color: #334155;
  line-height: 1.75;
}

.evidence-score-row {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  margin-bottom: 8px;
}

.evidence-chunk-id {
  margin-bottom: 8px;
  color: #64748b;
  font-family: "SFMono-Regular", Consolas, "Liberation Mono", monospace;
  font-size: 12px;
}

.evidence-raw-text {
  padding: 10px;
  border-radius: 6px;
  background: #eef2f7;
}

@media (max-width: 980px) {
  .diagnosis-input-grid,
  .diagnosis-result-grid,
  .report-columns {
    grid-template-columns: 1fr;
  }
}
</style>
