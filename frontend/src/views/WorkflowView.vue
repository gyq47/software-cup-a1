<script setup>
import {
  CircleCheck,
  DocumentChecked,
  Download,
  Printer,
  Tools,
  WarningFilled,
} from '@element-plus/icons-vue'
import { ElMessage } from 'element-plus'
import { computed, onMounted, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'

import { generateWorkflow } from '../api/workflow'

const route = useRoute()
const router = useRouter()
const task = ref('如何安装离合器')
const topK = ref(5)
const loading = ref(false)
const workflow = ref(null)
const complianceResult = ref(null)
const contexts = ref([])
const checkedSteps = ref([])
const checkedFinalItems = ref([])

const tools = computed(() => workflow.value?.tools || [])
const safetyNotices = computed(() => workflow.value?.safety_notices || [])
const steps = computed(() => workflow.value?.steps || [])
const finalCheck = computed(() => workflow.value?.final_check || [])
const references = computed(() => workflow.value?.references || [])
const evidenceSummary = computed(() => workflow.value?.evidence_summary || {})
const complianceWarnings = computed(() => complianceResult.value?.warnings || [])
const lowEvidenceSteps = computed(() => evidenceSummary.value.low_evidence_steps || [])
const progressPercent = computed(() => {
  const total = steps.value.length + finalCheck.value.length
  if (!total) return 0
  const done = checkedSteps.value.length + checkedFinalItems.value.length
  return Math.round((done / total) * 100)
})

onMounted(() => {
  const queryTask = route.query.task
  if (typeof queryTask === 'string' && queryTask.trim()) {
    task.value = queryTask
  }
})

const handleGenerate = async () => {
  const text = task.value.trim()
  if (!text) {
    ElMessage.warning('请输入检修任务')
    return
  }

  loading.value = true
  workflow.value = null
  complianceResult.value = null
  contexts.value = []
  checkedSteps.value = []
  checkedFinalItems.value = []

  try {
    const data = await generateWorkflow(text, topK.value)
    workflow.value = data.workflow
    complianceResult.value = data.compliance_result
    contexts.value = Array.isArray(data.contexts) ? data.contexts : []
    ElMessage.success('标准作业卡已生成')
  } catch (error) {
    ElMessage.error('标准作业卡生成失败，请检查后端服务')
  } finally {
    loading.value = false
  }
}

const handlePrint = () => {
  window.print()
}

const goFeedback = () => {
  router.push({
    path: '/feedback',
    query: {
      source_type: 'workflow',
      question: task.value,
    },
  })
}

const getRiskLevel = (risk) => {
  const text = String(risk || '')
  if (text.includes('高') || text.includes('严重') || text.includes('烫') || text.includes('夹') || text.includes('断电')) {
    return 'high'
  }
  if (text.includes('注意') || text.includes('检查') || text.includes('扭矩') || text.includes('泄漏')) {
    return 'medium'
  }
  return 'low'
}

const getRiskTagType = (risk) => {
  const level = getRiskLevel(risk)
  if (level === 'high') return 'danger'
  if (level === 'medium') return 'warning'
  return 'primary'
}

const getRiskLabel = (risk) => {
  const level = getRiskLevel(risk)
  if (level === 'high') return 'high'
  if (level === 'medium') return 'medium'
  return 'low'
}

const getWarningType = (level) => {
  if (level === 'high') return 'danger'
  if (level === 'medium') return 'warning'
  return 'info'
}

const hasStepEvidence = (step) => {
  return Array.isArray(step.references) && step.references.length > 0
}

const isLowEvidenceStep = (step) => {
  return lowEvidenceSteps.value.includes(step.step_no) || !hasStepEvidence(step)
}

const formatScore = (score) => {
  if (typeof score !== 'number') return '-'
  return score.toFixed(2)
}
</script>

<template>
  <section class="page workflow-field-page">
    <div class="workflow-hero no-print">
      <div>
        <p class="eyebrow">Workflow SOP</p>
        <h1>标准化检修作业卡</h1>
        <p>AI生成的工业设备检修指导流程</p>
      </div>
      <div class="hero-actions">
        <el-button :disabled="!workflow" @click="goFeedback">
          提交修正/补充步骤
        </el-button>
        <el-button :icon="Printer" :disabled="!workflow" @click="handlePrint">
          一键打印
        </el-button>
        <el-button type="primary" color="#111827" :icon="Download" :disabled="!workflow" @click="handlePrint">
          导出PDF
        </el-button>
      </div>
    </div>

    <el-card shadow="never" class="sop-query-card no-print">
      <div class="sop-query">
        <el-input
          v-model="task"
          size="large"
          placeholder="输入检修任务，例如：如何安装离合器"
          clearable
          @keydown.enter="handleGenerate"
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
          :icon="DocumentChecked"
          :loading="loading"
          @click="handleGenerate"
        >
          生成作业卡
        </el-button>
      </div>
    </el-card>

    <el-skeleton v-if="loading" :rows="10" animated class="sop-skeleton" />

    <el-empty
      v-else-if="!workflow"
      description="输入检修任务后生成工业现场标准作业卡"
      :image-size="120"
    />

    <div v-else class="sop-board">
      <el-card shadow="never" class="sop-info-card">
        <template #header>
          <div class="sop-card-header">
            <span>作业卡信息</span>
            <el-tag type="info">{{ contexts.length }} 个参考片段</el-tag>
          </div>
        </template>
        <h2>{{ workflow.title }}</h2>
        <p>{{ workflow.summary }}</p>
        <el-progress :percentage="progressPercent" :stroke-width="10" />
      </el-card>

      <div class="evidence-overview-grid">
        <el-card shadow="never" class="evidence-overview-card">
          <div class="evidence-metric">
            <span>参考文档数量</span>
            <strong>{{ evidenceSummary.main_files?.length || 0 }}</strong>
          </div>
        </el-card>
        <el-card shadow="never" class="evidence-overview-card">
          <div class="evidence-metric">
            <span>涉及页码</span>
            <strong>{{ evidenceSummary.referenced_pages?.join(' / ') || '-' }}</strong>
          </div>
        </el-card>
        <el-card shadow="never" class="evidence-overview-card">
          <div class="evidence-metric">
            <span>参考片段数量</span>
            <strong>{{ evidenceSummary.total_contexts || 0 }}</strong>
          </div>
        </el-card>
        <el-card shadow="never" class="evidence-overview-card warning">
          <div class="evidence-metric">
            <span>依据不足步骤</span>
            <strong>{{ lowEvidenceSteps.length }}</strong>
          </div>
        </el-card>
      </div>

      <div class="sop-layout">
        <main class="sop-main">
          <el-card shadow="never" class="sop-section-card">
            <template #header>
              <div class="sop-card-header">
                <span>检修步骤</span>
                <el-tag type="primary">{{ steps.length }} 步</el-tag>
              </div>
            </template>

            <el-timeline class="sop-timeline">
              <el-timeline-item
                v-for="step in steps"
                :key="step.step_no"
                placement="top"
                :timestamp="`STEP ${step.step_no}`"
              >
                <div class="field-step-card">
                  <div class="step-number">{{ step.step_no }}</div>
                  <div class="step-content">
                    <div class="step-topline">
                      <h3>{{ step.title }}</h3>
                      <el-checkbox-group v-model="checkedSteps">
                        <el-checkbox :label="step.step_no">完成</el-checkbox>
                      </el-checkbox-group>
                    </div>
                    <p class="step-description">{{ step.description }}</p>
                    <div class="step-grid">
                      <div class="step-field">
                        <span>检查项</span>
                        <strong>{{ step.check_item }}</strong>
                      </div>
                      <div class="step-field">
                        <span>参考依据</span>
                        <strong>{{ step.reference }}</strong>
                      </div>
                    </div>
                    <el-tag :type="getRiskTagType(step.risk)" effect="dark" class="risk-level-tag">
                      {{ getRiskLabel(step.risk) }} · {{ step.risk }}
                    </el-tag>

                    <div class="step-evidence-status">
                      <el-tag v-if="!isLowEvidenceStep(step)" type="success" effect="plain">
                        已关联手册依据
                      </el-tag>
                      <el-alert
                        v-else
                        title="知识库依据不足，建议由专业人员确认。"
                        type="warning"
                        :closable="false"
                        show-icon
                      />
                    </div>

                    <el-collapse v-if="hasStepEvidence(step)" class="evidence-collapse">
                      <el-collapse-item title="查看依据原文" :name="`step-${step.step_no}`">
                        <div
                          v-for="reference in step.references"
                          :key="`${reference.chunk_id}-${reference.page}`"
                          class="evidence-source-card"
                        >
                          <div class="evidence-source-head">
                            <div>
                              <strong>{{ reference.filename || '未知文件' }}</strong>
                              <el-tag type="primary" effect="dark">
                                第 {{ reference.page || '-' }} 页
                              </el-tag>
                            </div>
                            <div class="score-tags">
                              <el-tag type="success" effect="plain">
                                final {{ formatScore(reference.final_score) }}
                              </el-tag>
                              <el-tag type="warning" effect="plain">
                                bm25 {{ formatScore(reference.bm25_score) }}
                              </el-tag>
                              <el-tag type="info" effect="plain">
                                hits {{ reference.keyword_hits || 0 }}
                              </el-tag>
                            </div>
                          </div>
                          <div class="chunk-id">chunk_id: {{ reference.chunk_id || '-' }}</div>
                          <p class="evidence-content">{{ reference.content }}</p>
                        </div>
                      </el-collapse-item>
                    </el-collapse>
                  </div>
                </div>
              </el-timeline-item>
            </el-timeline>
          </el-card>

          <el-card shadow="never" class="sop-section-card">
            <template #header>
              <div class="sop-card-header">
                <span>完工检查</span>
                <el-icon><CircleCheck /></el-icon>
              </div>
            </template>
            <el-checkbox-group v-model="checkedFinalItems" class="final-list">
              <el-checkbox v-for="item in finalCheck" :key="item" :label="item">
                {{ item }}
              </el-checkbox>
            </el-checkbox-group>
          </el-card>

          <el-card shadow="never" class="sop-section-card">
            <template #header>
              <div class="sop-card-header">参考依据</div>
            </template>
            <div class="reference-list">
              <div v-for="item in references" :key="item" class="reference-item">
                {{ item }}
              </div>
            </div>
          </el-card>
        </main>

        <aside class="sop-side">
          <el-card shadow="never" class="sop-side-card">
            <template #header>
              <div class="sop-card-header">
                <span>工具清单</span>
                <el-icon><Tools /></el-icon>
              </div>
            </template>
            <div class="tool-tags">
              <el-tag v-for="item in tools" :key="item" effect="plain">
                {{ item }}
              </el-tag>
            </div>
          </el-card>

          <el-card shadow="never" class="sop-side-card safety-card">
            <template #header>
              <div class="sop-card-header">
                <span>安全提醒</span>
                <el-icon><WarningFilled /></el-icon>
              </div>
            </template>
            <el-alert
              v-for="item in safetyNotices"
              :key="item"
              :title="item"
              type="error"
              :closable="false"
              show-icon
              class="safety-alert"
            />
          </el-card>

          <el-card shadow="never" class="sop-side-card">
            <template #header>
              <div class="sop-card-header">合规校验</div>
            </template>
            <el-result
              v-if="complianceResult?.passed"
              icon="success"
              title="校验通过"
              :sub-title="complianceResult.summary"
            />
            <div v-else class="compliance-warning-list">
              <el-alert
                :title="complianceResult?.summary || '存在合规风险'"
                type="warning"
                :closable="false"
                show-icon
              />
              <div
                v-for="warning in complianceWarnings"
                :key="warning.rule_id"
                class="compliance-warning"
              >
                <el-tag :type="getWarningType(warning.level)" effect="dark">
                  {{ warning.level }}
                </el-tag>
                <div>
                  <strong>{{ warning.message }}</strong>
                  <p>缺失要求：{{ warning.missing_required?.join(' / ') || '-' }}</p>
                </div>
              </div>
            </div>
          </el-card>

          <el-card shadow="never" class="sop-side-card evidence-risk-card">
            <template #header>
              <div class="sop-card-header">知识依据风险</div>
            </template>
            <el-alert
              v-if="!lowEvidenceSteps.length"
              title="所有步骤均已关联知识库片段"
              type="success"
              :closable="false"
              show-icon
            />
            <el-alert
              v-else
              :title="`步骤 ${lowEvidenceSteps.join('、')} 依据不足`"
              description="依据不足不等同于合规失败，表示该步骤缺少明确的知识库原文支撑。"
              type="warning"
              :closable="false"
              show-icon
            />
          </el-card>
        </aside>
      </div>
    </div>
  </section>
</template>

<style scoped>
.workflow-field-page {
  gap: 18px;
}

.workflow-hero {
  display: flex;
  align-items: flex-end;
  justify-content: space-between;
  gap: 18px;
  padding: 22px 24px;
  border: 1px solid #1f2a3a;
  border-radius: 10px;
  background: #111827;
  color: #ffffff;
  box-shadow: 0 12px 28px rgba(15, 23, 42, 0.18);
}

.workflow-hero h1 {
  margin: 6px 0 8px;
  font-size: 30px;
  line-height: 1.2;
}

.workflow-hero p:last-child {
  margin: 0;
  color: #aeb8c8;
}

.hero-actions {
  display: flex;
  gap: 10px;
}

.sop-query-card,
.sop-info-card,
.sop-section-card,
.sop-side-card,
.evidence-overview-card {
  border: 1px solid #dbe2ea;
  border-radius: 10px;
  box-shadow: 0 8px 22px rgba(15, 23, 42, 0.08);
}

.sop-query {
  display: grid;
  grid-template-columns: minmax(0, 1fr) 140px 150px;
  gap: 12px;
}

.sop-board {
  display: flex;
  flex-direction: column;
  gap: 18px;
}

.evidence-overview-grid {
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: 14px;
}

.evidence-overview-card.warning {
  border-color: #facc15;
}

.evidence-metric {
  display: flex;
  min-height: 72px;
  flex-direction: column;
  justify-content: center;
  gap: 8px;
}

.evidence-metric span {
  color: #64748b;
  font-size: 13px;
  font-weight: 700;
}

.evidence-metric strong {
  color: #111827;
  font-size: 22px;
  line-height: 1.25;
}

.sop-info-card h2 {
  margin: 0 0 8px;
  color: #111827;
  font-size: 24px;
}

.sop-info-card p {
  margin: 0 0 18px;
  color: #475569;
  line-height: 1.8;
}

.sop-card-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  color: #172033;
  font-weight: 800;
}

.sop-layout {
  display: grid;
  grid-template-columns: minmax(0, 1fr) 360px;
  gap: 18px;
  align-items: start;
}

.sop-main,
.sop-side {
  display: flex;
  flex-direction: column;
  gap: 16px;
}

.sop-timeline {
  padding-top: 6px;
}

.field-step-card {
  position: relative;
  display: flex;
  gap: 16px;
  padding: 16px;
  border: 1px solid #d7e0ec;
  border-left: 4px solid #2563eb;
  border-radius: 10px;
  background: #f8fafc;
  box-shadow: 0 8px 18px rgba(15, 23, 42, 0.08);
  transition: border-color 0.18s ease, box-shadow 0.18s ease, transform 0.18s ease;
}

.field-step-card:hover {
  border-color: #2563eb;
  box-shadow: 0 14px 28px rgba(37, 99, 235, 0.14);
  transform: translateY(-1px);
}

.step-number {
  display: flex;
  width: 42px;
  height: 42px;
  flex: 0 0 42px;
  align-items: center;
  justify-content: center;
  border-radius: 50%;
  background: #111827;
  color: #ffffff;
  font-weight: 900;
}

.step-content {
  min-width: 0;
  flex: 1;
}

.step-topline {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 12px;
}

.step-topline h3 {
  margin: 0;
  color: #111827;
  font-size: 18px;
}

.step-description {
  margin: 10px 0 14px;
  color: #334155;
  line-height: 1.8;
}

.step-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 12px;
  margin-bottom: 12px;
}

.step-field {
  padding: 12px;
  border: 1px solid #e2e8f0;
  border-radius: 8px;
  background: #ffffff;
}

.step-field span {
  display: block;
  margin-bottom: 6px;
  color: #64748b;
  font-size: 12px;
  font-weight: 700;
}

.step-field strong {
  color: #172033;
  line-height: 1.6;
}

.risk-level-tag {
  max-width: 100%;
  height: auto;
  min-height: 30px;
  white-space: normal;
}

.step-evidence-status {
  margin-top: 12px;
}

.evidence-collapse {
  margin-top: 12px;
  border-top: 1px solid #dbe2ea;
}

.evidence-source-card {
  padding: 12px;
  border: 1px solid #dbe2ea;
  border-radius: 8px;
  background: #f1f5f9;
}

.evidence-source-card + .evidence-source-card {
  margin-top: 10px;
}

.evidence-source-head {
  display: flex;
  justify-content: space-between;
  gap: 12px;
}

.evidence-source-head > div:first-child,
.score-tags {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 8px;
}

.chunk-id {
  margin-top: 8px;
  color: #64748b;
  font-family: "SFMono-Regular", Consolas, "Liberation Mono", monospace;
  font-size: 12px;
}

.evidence-content {
  margin: 10px 0 0;
  color: #334155;
  line-height: 1.8;
}

.tool-tags {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
}

.safety-card {
  border-color: #fecaca;
}

.safety-alert {
  margin-bottom: 10px;
}

.compliance-warning-list {
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.compliance-warning {
  display: flex;
  gap: 10px;
  padding: 12px;
  border: 1px solid #fed7aa;
  border-radius: 8px;
  background: #fff7ed;
}

.compliance-warning p {
  margin: 6px 0 0;
  color: #9a3412;
}

.final-list {
  display: flex;
  flex-direction: column;
  gap: 10px;
}

.reference-list {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.reference-item {
  padding: 12px;
  border: 1px solid #e2e8f0;
  border-radius: 8px;
  background: #f8fafc;
  color: #475569;
}

.sop-skeleton {
  padding: 20px;
  border: 1px solid #dbe2ea;
  border-radius: 10px;
  background: #ffffff;
}

@media (max-width: 1120px) {
  .sop-layout,
  .sop-query,
  .step-grid,
  .evidence-overview-grid {
    grid-template-columns: 1fr;
  }

  .workflow-hero {
    align-items: flex-start;
    flex-direction: column;
  }
}

@media print {
  .no-print,
  .sidebar,
  .topbar {
    display: none !important;
  }

  .main-area {
    margin-left: 0 !important;
  }

  .content {
    padding: 0 !important;
  }

  .sop-layout {
    grid-template-columns: 1fr;
  }

  .sop-info-card,
  .sop-section-card,
  .sop-side-card,
  .field-step-card {
    box-shadow: none;
    break-inside: avoid;
  }
}
</style>
