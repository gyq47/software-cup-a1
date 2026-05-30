<script setup>
import { Camera, DocumentChecked, UploadFilled, WarningFilled } from '@element-plus/icons-vue'
import { ElMessage } from 'element-plus'
import { computed, reactive, ref } from 'vue'

import { buildApiUrl } from '../api/config'
import { confirmDiagnosis } from '../api/diagnosis'
import { getGraphSubgraph } from '../api/graph'
import {
  analyzeFault,
  generateWorkbenchWorkflow,
  getHistoryReferences,
  submitCorrection,
} from '../api/workbench'
import { useAuthStore } from '../stores/auth'

const auth = useAuthStore()
const loading = ref(false)
const workflowLoading = ref(false)
const submitting = ref(false)
const imageInputRef = ref(null)
const imageFile = ref(null)
const previewUrl = ref('')
const analysisResult = ref(null)
const workflowResult = ref(null)
const historyReferences = ref([])
const graphAssociation = ref({ nodes: [], edges: [] })
const selectedAlarmCandidates = ref([])
const alarmConfirmNote = ref('')
const alarmSelectionConfirmed = ref(false)
const pagePreviewVisible = ref(false)
const pagePreviewUrl = ref('')
const pagePreviewTitle = ref('')

const form = reactive({
  deviceModel: '',
  fault: 'X轴无法回零，系统报警，无法进入自动加工。',
  alarmCode: '',
  level: '一级检修（小修 / 故障抢修）',
  mode: '基础模式',
})

const correction = reactive({
  inaccurate: '',
  actualReason: '',
  actualSolution: '',
  experience: '',
  type: '现场经验补充',
})

const levelDescriptions = {
  '一级检修（小修 / 故障抢修）': '快速恢复设备运行，聚焦报警直接原因，步骤精炼，优先恢复生产。',
  '二级检修（中修 / 计划检修）': '消除潜在隐患，结合上下游模块、参数和电气机械状态进行关联排查。',
  '三级检修（大修 / 项修）': '面向核心部件维修和全面恢复，强化断电挂牌、联锁确认、协同检修和测试记录。',
}

const modeDescription = computed(() => {
  if (form.mode === '增强模式') {
    return '当前启用增强模式：系统将在 OCR 结果基础上，进一步调用视觉模型辅助识别驱动器状态灯、PLC模块状态灯、接线端子状态、模块连接状态和报警指示状态等信息。'
  }
  return '当前使用基础模式：系统主要通过 OCR 与规则引擎提取报警代码、参数号、PLC地址、设备型号和界面文字，并结合知识库完成检索。'
})

const diagnosis = computed(() => analysisResult.value?.diagnosis || {})
const evidenceItems = computed(() => [
  ...(analysisResult.value?.evidence_items || []),
  ...(workflowResult.value?.evidence_items || []),
])
const retrievalFilter = computed(() => (
  analysisResult.value?.retrieval_filter
  || workflowResult.value?.retrieval_filter
  || {}
))
const toolTrace = computed(() => [
  ...(analysisResult.value?.tool_trace || []),
  ...(workflowResult.value?.tool_trace || []),
])
const graphContext = computed(() => (
  analysisResult.value?.graph_context
  || workflowResult.value?.graph_context
  || graphAssociation.value
  || {}
))
const workflow = computed(() => workflowResult.value?.workflow || null)
const associationPath = computed(() => (
  graphContext.value.expanded_nodes?.length
    ? graphContext.value.expanded_nodes.map((node) => node.name)
    : graphContext.value.nodes?.length
      ? graphContext.value.nodes.map((node) => node.name)
    : []
))
const imageFileName = computed(() => imageFile.value?.name || '')
const imageFileSize = computed(() => {
  if (!imageFile.value?.size) {
    return ''
  }
  const size = imageFile.value.size / 1024
  return size >= 1024 ? `${(size / 1024).toFixed(2)} MB` : `${size.toFixed(1)} KB`
})

const openImagePicker = () => {
  imageInputRef.value?.click()
}

const handleImageChange = (event) => {
  const file = event.target.files?.[0]
  if (!file) {
    return
  }
  if (!file.type.startsWith('image/')) {
    ElMessage.error('请上传报警界面或设备现场图片')
    event.target.value = ''
    return false
  }
  if (previewUrl.value) {
    URL.revokeObjectURL(previewUrl.value)
  }
  imageFile.value = file
  previewUrl.value = URL.createObjectURL(file)
  ElMessage.success('图片已选择')
  event.target.value = ''
}

const removeImage = () => {
  if (previewUrl.value) {
    URL.revokeObjectURL(previewUrl.value)
  }
  imageFile.value = null
  previewUrl.value = ''
  if (imageInputRef.value) {
    imageInputRef.value.value = ''
  }
}

const runAnalysis = async () => {
  loading.value = true
  alarmSelectionConfirmed.value = false
  try {
    analysisResult.value = await analyzeFault({
      image: imageFile.value,
      text: form.fault,
      deviceModel: form.deviceModel,
      alarmCode: form.alarmCode,
      level: form.level,
      mode: form.mode,
    })
    initializeAlarmCandidateSelection()
    historyReferences.value = await getHistoryReferences()
    if (!analysisResult.value?.graph_context) {
      await loadGraphAssociation()
    }
    ElMessage.success('辅助分析已完成')
  } catch (error) {
    ElMessage.error('辅助分析失败，请检查后端服务')
  } finally {
    loading.value = false
  }
}

const loadGraphAssociation = async () => {
  try {
    graphAssociation.value = await getGraphSubgraph(form.fault || form.alarmCode || '轴无法回零', 2, form.deviceModel)
  } catch (error) {
    graphAssociation.value = { nodes: [], edges: [] }
  }
}

const generateCard = async () => {
  workflowLoading.value = true
  try {
    const task = `${form.deviceModel} ${form.alarmCode} ${form.fault} ${form.level}`
    workflowResult.value = await generateWorkbenchWorkflow(task, 5, form.deviceModel)
    ElMessage.success('标准作业卡已生成')
  } catch (error) {
    ElMessage.error('标准作业卡生成失败')
  } finally {
    workflowLoading.value = false
  }
}

const submitWorkbenchCorrection = async () => {
  if (!correction.actualSolution && !correction.experience && !correction.inaccurate) {
    ElMessage.warning('请填写修正或经验补充内容')
    return
  }

  submitting.value = true
  try {
    await submitCorrection({
      original_question: `${form.deviceModel} ${form.alarmCode} ${form.fault}`,
      original_answer: diagnosis.value.summary || workflow.value?.summary || '',
      correction_type: 'other',
      correction_text: [
        correction.inaccurate,
        correction.actualReason,
        correction.actualSolution,
        correction.experience,
        correction.type,
      ].filter(Boolean).join('\n'),
      related_device: form.deviceModel,
      related_fault: form.fault,
    })
    ElMessage.success('已提交给设备工程师审核，当前状态：待审核')
  } catch (error) {
    ElMessage.error('提交失败，请检查后端服务')
  } finally {
    submitting.value = false
  }
}

const scoreText = (value) => {
  const number = Number(value)
  return Number.isFinite(number) ? number.toFixed(2) : '-'
}
const evidenceSourceLabel = (item) => (
  item?.source_type === 'feedback_case' || item?.evidence_type === 'feedback_case'
    ? '审核案例'
    : item?.source_type === 'manual_image' || item?.evidence_type === 'manual_image'
      ? '手册图片'
      : '维修手册'
)
const getPagePreviewUrl = (item) => {
  const previewUrlValue = item?.preview_url || ''
  if (previewUrlValue.startsWith('http')) {
    return previewUrlValue
  }
  if (previewUrlValue.startsWith('/')) {
    return buildApiUrl(previewUrlValue)
  }
  if (item?.page_image_path) {
    return buildApiUrl(`/api/manual/page-image?path=${encodeURIComponent(item.page_image_path)}`)
  }
  return ''
}
const openPagePreview = (item) => {
  const url = getPagePreviewUrl(item)
  if (!url) {
    ElMessage.info('该依据暂未生成原文页截图')
    return
  }
  pagePreviewUrl.value = url
  pagePreviewTitle.value = `${item.pdf_filename || item.filename || '维修手册'} 第 ${item.page_number || item.page || '-'} 页`
  pagePreviewVisible.value = true
}

const alarmCandidates = computed(() => analysisResult.value?.vision_result?.alarm_candidates || [])
const alarmCandidateKey = (candidate, index) => `${candidate.code || candidate.text || 'alarm'}-${index}`
const selectedAlarmCandidateItems = computed(() => alarmCandidates.value.filter((candidate, index) => (
  selectedAlarmCandidates.value.includes(alarmCandidateKey(candidate, index))
)))
const confirmedAlarmCodes = computed(() => (
  analysisResult.value?.confirmed_alarm_codes?.length
    ? analysisResult.value.confirmed_alarm_codes
    : selectedAlarmCandidateItems.value.map((candidate) => candidate.code).filter(Boolean)
))
const confirmedAlarmTexts = computed(() => (
  analysisResult.value?.confirmed_alarm_texts?.length
    ? analysisResult.value.confirmed_alarm_texts
    : selectedAlarmCandidateItems.value.map((candidate) => candidate.text).filter(Boolean)
))
const initializeAlarmCandidateSelection = () => {
  const candidates = analysisResult.value?.vision_result?.alarm_candidates || []
  if (!candidates.length) {
    selectedAlarmCandidates.value = []
    alarmConfirmNote.value = ''
    alarmSelectionConfirmed.value = false
    return
  }

  const recommended = candidates
    .map((candidate, index) => ({ candidate, index }))
    .filter(({ candidate }) => candidate.is_current)
    .map(({ candidate, index }) => alarmCandidateKey(candidate, index))

  selectedAlarmCandidates.value = recommended.length
    ? recommended
    : [alarmCandidateKey(candidates[0], 0)]
}
const confirmAlarmCandidates = () => {
  if (!selectedAlarmCandidateItems.value.length) {
    ElMessage.warning('请至少选择一个报警候选')
    return
  }

  loading.value = true
  confirmDiagnosis({
    device_model: form.deviceModel,
    mode: form.mode,
    level: form.level,
    selected_alarm_codes: selectedAlarmCandidateItems.value
      .map((candidate) => candidate.code)
      .filter(Boolean),
    selected_alarm_texts: selectedAlarmCandidateItems.value
      .map((candidate) => candidate.text)
      .filter(Boolean),
    user_confirm_note: alarmConfirmNote.value,
    fault_description: form.fault,
    vision_result: analysisResult.value?.vision_result || {},
  }).then((response) => {
    analysisResult.value = response
    alarmSelectionConfirmed.value = true
    ElMessage.success('已基于确认报警重新生成诊断')
  }).catch(() => {
    ElMessage.error('确认报警诊断失败，请检查后端服务')
  }).finally(() => {
    loading.value = false
  })
}
const resetAlarmSelection = () => {
  alarmSelectionConfirmed.value = false
}
const graphPaths = computed(() => graphContext.value.paths || [])
const graphWarnings = computed(() => graphContext.value.warnings || analysisResult.value?.graph_warnings || [])
const toolStatusType = (status) => {
  if (status === 'success') return 'success'
  if (status === 'failed') return 'danger'
  return 'info'
}

const structuredAnswer = computed(() => analysisResult.value?.structured_answer || null)
const faultSummary = computed(() => (
  structuredAnswer.value?.fault_summary
  || diagnosis.value.summary
  || diagnosis.value.analysis_text
  || analysisResult.value?.answer
  || ''
))
const possibleCauses = computed(() => (
  structuredAnswer.value?.possible_causes
  || diagnosis.value.fault_analysis
  || []
))
const operationSteps = computed(() => (
  structuredAnswer.value?.operation_steps
  || []
))
const recommendedSteps = computed(() => {
  if (diagnosis.value.inspection_steps?.length) {
    return diagnosis.value.inspection_steps
  }
  return operationSteps.value.map((step) => step.title || step.description).filter(Boolean)
})
const riskWarnings = computed(() => (
  structuredAnswer.value?.risk_warnings
  || diagnosis.value.safety_notices
  || []
))
const requiredTools = computed(() => structuredAnswer.value?.required_tools || [])
const manualReferences = computed(() => structuredAnswer.value?.manual_references || [])
const diagnosisConfidence = computed(() => structuredAnswer.value?.diagnosis_confidence || '')
const evidenceMetrics = computed(() => structuredAnswer.value?.evidence_metrics || {})
const isEvidenceInsufficient = computed(() => diagnosisConfidence.value === 'insufficient')
const confidenceProfile = computed(() => {
  const profiles = {
    high: { label: '高可信', type: 'success' },
    medium: { label: '中等可信', type: 'primary' },
    low: { label: '低可信', type: 'warning' },
    insufficient: { label: '手册依据不足', type: 'danger' },
  }
  return profiles[diagnosisConfidence.value] || { label: '待评估', type: 'info' }
})
const displayWorkflow = computed(() => {
  if (isEvidenceInsufficient.value) {
    return null
  }
  if (workflow.value) {
    return workflow.value
  }
  if (!operationSteps.value.length) {
    return null
  }
  return {
    title: `${form.deviceModel || '设备'} 标准作业卡`,
    tools: requiredTools.value,
    steps: operationSteps.value.map((step, index) => ({
      step_no: step.step_no || index + 1,
      title: step.title || `步骤 ${index + 1}`,
      description: step.description || String(step),
      risk: step.risk || '',
      reference: step.reference || step.manual_references?.[0]?.chunk_id || '',
    })),
  }
})
</script>

<template>
  <section class="page workbench-page">
    <div class="workbench-hero">
      <div>
        <p class="eyebrow">Maintenance Copilot</p>
        <h1>工业检修工作台</h1>
        <p>面向数控设备现场检修的智能导航与标准作业指导。</p>
      </div>
      <div class="status-strip">
        <el-tag effect="dark">{{ auth.display_name }}</el-tag>
        <el-tag type="success" effect="dark">{{ auth.role === 'worker' ? '检修人员' : auth.role === 'expert' ? '设备工程师' : '系统管理员' }}</el-tag>
        <el-tag type="warning" effect="dark">{{ form.mode }}</el-tag>
        <el-tag type="info" effect="dark">{{ form.level }}</el-tag>
        <el-tag type="primary" effect="dark">{{ form.deviceModel || '未选择设备' }}</el-tag>
      </div>
    </div>

    <div class="workbench-grid">
      <el-card shadow="never" class="industrial-card input-panel">
        <template #header>现场输入</template>
        <div class="form-stack">
          <el-input v-model="form.deviceModel" size="large" placeholder="设备型号，例如 SINUMERIK 828D" />
          <el-input v-model="form.alarmCode" size="large" placeholder="报警代码 / 错误码，可选" />
          <el-input
            v-model="form.fault"
            type="textarea"
            :rows="5"
            resize="none"
            placeholder="故障描述，例如：X轴无法回零，系统报警，无法进入自动加工。"
          />
          <input
            ref="imageInputRef"
            class="hidden-file-input"
            type="file"
            accept="image/*"
            @change="handleImageChange"
          />
          <button class="image-upload-zone" type="button" @click="openImagePicker">
            <el-icon class="el-icon--upload"><UploadFilled /></el-icon>
            <span>
              {{ imageFileName ? `已选择：${imageFileName}` : '上传报警界面、HMI 面板、PLC 状态界面或接线照片' }}
            </span>
          </button>
          <div v-if="imageFile" class="upload-feedback">
            <img v-if="previewUrl" :src="previewUrl" class="preview" alt="报警图片预览" />
            <div class="upload-meta">
              <div>
                <strong>{{ imageFileName }}</strong>
                <p>{{ imageFileSize }}</p>
              </div>
              <div class="upload-actions">
                <el-tag type="success" effect="dark">上传成功</el-tag>
                <el-button size="small" plain type="danger" @click="removeImage">移除图片</el-button>
              </div>
            </div>
          </div>
          <el-select v-model="form.level" size="large">
            <el-option v-for="item in Object.keys(levelDescriptions)" :key="item" :label="item" :value="item" />
          </el-select>
          <el-alert :title="levelDescriptions[form.level]" type="info" :closable="false" show-icon />
          <el-segmented v-model="form.mode" :options="['基础模式', '增强模式']" />
          <el-alert :title="modeDescription" type="warning" :closable="false" show-icon />
          <div class="action-row">
            <el-button type="primary" color="#1d4ed8" size="large" :loading="loading" :icon="Camera" @click="runAnalysis">
              开始辅助分析
            </el-button>
            <el-button color="#111827" size="large" :loading="workflowLoading" :icon="DocumentChecked" @click="generateCard">
              生成标准作业卡
            </el-button>
          </div>
        </div>
      </el-card>

      <main class="result-panel">
        <el-card shadow="never" class="industrial-card">
          <template #header>AI 辅助分析结果</template>
          <el-skeleton v-if="loading" :rows="6" animated />
          <el-empty v-else-if="!analysisResult" description="输入故障信息后开始辅助分析" />
          <div v-else class="analysis-grid">
            <div v-if="alarmCandidates.length" class="alarm-candidate-card">
              <div class="alarm-candidate-head">
                <div>
                  <h3>{{ alarmSelectionConfirmed ? '已确认诊断对象' : '识别到的报警候选' }}</h3>
                  <p>{{ alarmSelectionConfirmed ? '系统已基于以下报警重新生成诊断。' : '请确认当前需要诊断的故障，可单选或多选。' }}</p>
                </div>
                <el-tag type="primary" effect="dark">{{ alarmCandidates.length }} 条候选</el-tag>
              </div>
              <div v-if="alarmSelectionConfirmed" class="confirmed-alarm-summary">
                <div>
                  <span>已选报警代码</span>
                  <div class="alarm-candidate-tags">
                    <el-tag v-for="code in confirmedAlarmCodes" :key="code" type="danger" effect="dark">{{ code }}</el-tag>
                    <el-tag v-if="!confirmedAlarmCodes.length" type="info">无代码</el-tag>
                  </div>
                </div>
                <div>
                  <span>已选报警文本</span>
                  <p>{{ confirmedAlarmTexts.join('；') || '无报警文本' }}</p>
                </div>
                <div>
                  <span>用户补充说明</span>
                  <p>{{ alarmConfirmNote || '无补充说明' }}</p>
                </div>
                <div v-if="analysisResult.confirmed_query">
                  <span>确认后检索 Query</span>
                  <p class="chunk">{{ analysisResult.confirmed_query }}</p>
                </div>
                <div class="alarm-candidate-actions">
                  <el-button plain @click="resetAlarmSelection">重新选择</el-button>
                </div>
              </div>
              <template v-else>
                <el-checkbox-group v-model="selectedAlarmCandidates" class="alarm-candidate-list">
                  <label
                    v-for="(candidate, index) in alarmCandidates"
                    :key="alarmCandidateKey(candidate, index)"
                    class="alarm-candidate-item"
                  >
                    <el-checkbox :value="alarmCandidateKey(candidate, index)" />
                    <div class="alarm-candidate-body">
                      <div class="alarm-candidate-title">
                        <strong>{{ candidate.code || '未识别代码' }}</strong>
                        <span>{{ candidate.text || '暂无报警文本' }}</span>
                      </div>
                      <div class="alarm-candidate-tags">
                        <el-tag size="small" :type="candidate.confidence === 'high' ? 'success' : candidate.confidence === 'low' ? 'warning' : 'info'">
                          {{ candidate.confidence || 'medium' }}
                        </el-tag>
                        <el-tag v-if="candidate.is_current" size="small" type="danger" effect="dark">推荐当前故障</el-tag>
                        <el-tag size="small" effect="plain">{{ candidate.source || 'image' }}</el-tag>
                      </div>
                      <p>{{ candidate.reason || '需要用户确认' }}</p>
                    </div>
                  </label>
                </el-checkbox-group>
                <el-input
                  v-model="alarmConfirmNote"
                  type="textarea"
                  :rows="3"
                  resize="none"
                  placeholder="例如：当前仍存在的是 400007 和 400000，150202 是启动过程报警。"
                />
                <div class="alarm-candidate-actions">
                  <el-button type="primary" color="#1d4ed8" @click="confirmAlarmCandidates">确认选择</el-button>
                </div>
              </template>
            </div>
            <el-alert :title="faultSummary" type="info" :closable="false" show-icon />
            <div v-if="diagnosisConfidence" class="confidence-card">
              <div class="confidence-head">
                <div>
                  <h3>诊断可信度</h3>
                  <p>{{ structuredAnswer?.evidence_strength || '等待手册依据评估' }}</p>
                </div>
                <el-tag :type="confidenceProfile.type" effect="dark">{{ confidenceProfile.label }}</el-tag>
              </div>
              <div class="confidence-metrics">
                <span>引用覆盖：{{ structuredAnswer?.manual_coverage || '暂无' }}</span>
                <span>明确报警依据：{{ evidenceMetrics.has_explicit_alarm ? '是' : '否' }}</span>
                <span>诊断手册命中：{{ evidenceMetrics.has_diagnosis_manual ? '是' : '否' }}</span>
                <span>编程污染：{{ evidenceMetrics.has_programming_pollution ? '存在' : '未见明显污染' }}</span>
              </div>
              <el-alert
                v-if="structuredAnswer?.fallback_notice"
                :title="structuredAnswer.fallback_notice"
                :type="isEvidenceInsufficient ? 'error' : 'warning'"
                :closable="false"
                show-icon
              />
            </div>
            <div class="result-block">
              <h3>可能关联模块</h3>
              <el-tag v-for="item in ['回零开关', 'PLC输入信号', '伺服驱动', '急停安全回路']" :key="item" effect="plain">{{ item }}</el-tag>
            </div>
            <div class="result-block">
              <h3>可能原因</h3>
              <p v-for="item in possibleCauses" :key="item">{{ item }}</p>
              <el-empty v-if="!possibleCauses.length" description="暂无明确原因" :image-size="72" />
            </div>
            <div class="result-block">
              <h3>推荐排查顺序</h3>
              <p v-for="item in recommendedSteps" :key="item">{{ item }}</p>
              <el-empty v-if="!recommendedSteps.length" description="暂无排查顺序" :image-size="72" />
            </div>
            <div class="result-block risk">
              <h3><el-icon><WarningFilled /></el-icon> 风险提示</h3>
              <p v-for="item in riskWarnings" :key="item">{{ item }}</p>
              <el-empty v-if="!riskWarnings.length" description="暂无风险提示" :image-size="72" />
            </div>
            <div class="result-block">
              <h3>所需工具</h3>
              <div class="tool-row">
                <el-tag v-for="tool in requiredTools" :key="tool" effect="plain">{{ tool }}</el-tag>
              </div>
              <el-empty v-if="!requiredTools.length" description="手册未明确工具清单" :image-size="72" />
            </div>
            <div class="result-block">
              <h3>手册依据</h3>
              <p v-for="item in manualReferences" :key="`${item.filename}-${item.page}-${item.chunk_id}`">
                {{ item.source_type === 'feedback_case' ? '审核案例' : '维修手册' }}：
                {{ item.filename || item.file || '未知来源' }} {{ item.page ? `第 ${item.page} 页` : '' }}：{{ item.evidence || item.chunk_id }}
                <span v-if="item.device_model">（来源设备：{{ item.device_model }}）</span>
              </p>
              <el-empty v-if="!manualReferences.length" description="暂无结构化手册依据" :image-size="72" />
            </div>
            <div v-if="toolTrace.length" class="result-block tool-trace-block">
              <h3>工具链执行过程</h3>
              <div class="tool-trace-list">
                <div v-for="tool in toolTrace" :key="`${tool.tool_name}-${tool.output_summary}`" class="tool-trace-item">
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
            </div>
          </div>
        </el-card>

        <el-card shadow="never" class="industrial-card">
          <template #header>标准作业卡步骤流</template>
          <el-skeleton v-if="workflowLoading" :rows="7" animated />
          <el-alert
            v-else-if="isEvidenceInsufficient"
            title="当前无法生成可靠标准作业卡"
            description="系统未检索到足够手册依据，请补充明确报警代码、设备型号或查看原始手册后再生成作业卡。"
            type="error"
            :closable="false"
            show-icon
          />
          <el-empty v-else-if="!displayWorkflow" description="生成后在此查看嵌入式标准作业卡" />
          <div v-else class="workflow-card">
            <div class="workflow-title-row">
              <h2>{{ displayWorkflow.title }}</h2>
              <el-tag type="danger" effect="dark">风险等级：medium</el-tag>
            </div>
            <div class="tool-row">
              <el-tag v-for="tool in displayWorkflow.tools" :key="tool" effect="plain">{{ tool }}</el-tag>
            </div>
            <el-timeline>
              <el-timeline-item v-for="step in displayWorkflow.steps" :key="step.step_no" :timestamp="`步骤 ${step.step_no}`">
                <div class="sop-step">
                  <h3>{{ step.title }}</h3>
                  <p>{{ step.description }}</p>
                  <el-alert :title="step.risk || '按现场安全规范执行'" type="warning" :closable="false" />
                  <div class="step-foot">
                    <span>参考依据：{{ step.reference || '维修手册依据不足' }}</span>
                    <el-checkbox>完成</el-checkbox>
                  </div>
                </div>
              </el-timeline-item>
            </el-timeline>
          </div>
        </el-card>
      </main>

      <aside class="assist-panel">
        <el-card shadow="never" class="industrial-card">
          <el-tabs>
            <el-tab-pane label="手册依据">
              <el-alert
                v-if="retrievalFilter.filter_fallback"
                :title="retrievalFilter.filter_message"
                type="warning"
                :closable="false"
                show-icon
                class="filter-alert"
              />
              <el-empty v-if="!evidenceItems.length" description="暂无手册依据" />
              <el-collapse v-else>
                <el-collapse-item v-for="(item, index) in evidenceItems" :key="item.chunk_id || index" :name="index">
                  <template #title>
                    <span class="evidence-title">{{ item.filename || '未知手册' }}</span>
                    <el-tag :type="evidenceSourceLabel(item) === '审核案例' ? 'success' : 'primary'">
                      {{ evidenceSourceLabel(item) }}
                    </el-tag>
                    <el-tag v-if="item.device_model" type="info">来源设备：{{ item.device_model }}</el-tag>
                    <el-tag type="primary">第 {{ item.page || '-' }} 页</el-tag>
                  </template>
                  <div class="evidence-card">
                    <div class="score-row">
                      <el-tag type="success">final {{ scoreText(item.final_score) }}</el-tag>
                      <el-tag type="warning">hits {{ item.keyword_hits || 0 }}</el-tag>
                      <el-tag type="info">bm25 {{ scoreText(item.bm25_score) }}</el-tag>
                    </div>
                    <p class="chunk">chunk_id: {{ item.chunk_id || '-' }}</p>
                    <img
                      v-if="evidenceSourceLabel(item) === '手册图片' && getPagePreviewUrl(item)"
                      :src="getPagePreviewUrl(item)"
                      class="evidence-thumb"
                      alt="手册图片缩略图"
                    />
                    <p>{{ item.content }}</p>
                    <div class="evidence-actions">
                      <el-button
                        v-if="getPagePreviewUrl(item)"
                        size="small"
                        type="primary"
                        plain
                        @click="openPagePreview(item)"
                      >
                        查看原文页
                      </el-button>
                      <el-tag v-else-if="evidenceSourceLabel(item) === '审核案例'" type="success" effect="plain">
                        经验案例，无 PDF 页截图
                      </el-tag>
                      <el-alert
                        v-else
                        title="暂未生成页面预览，可根据文件名和页码定位原始手册。"
                        type="info"
                        :closable="false"
                      />
                    </div>
                  </div>
                </el-collapse-item>
              </el-collapse>
            </el-tab-pane>
            <el-tab-pane label="关联分析">
              <el-alert
                v-if="!graphContext.enabled"
                :title="graphWarnings[0] || '未匹配到关联图谱节点'"
                type="info"
                :closable="false"
                show-icon
                class="filter-alert"
              />
              <div v-if="graphContext.seed_nodes?.length" class="alarm-candidate-tags">
                <el-tag v-for="seed in graphContext.seed_nodes" :key="seed.id" type="warning" effect="plain">
                  seed: {{ seed.name }}
                </el-tag>
              </div>
              <el-empty v-if="!associationPath.length" description="暂无图谱关联路径" />
              <div class="graph-path">
                <template v-for="(node, index) in associationPath" :key="node">
                  <div class="path-node">{{ node }}</div>
                  <div v-if="index < associationPath.length - 1" class="path-arrow">↓</div>
                </template>
              </div>
              <div v-if="graphPaths.length" class="edge-list-mini">
                <div v-for="path in graphPaths" :key="`${path.source}-${path.relation}-${path.target}`" class="edge-mini">
                  <el-tag size="small" type="primary" effect="plain">{{ path.relation }}</el-tag>
                  <span>{{ path.source }} → {{ path.target }}</span>
                  <small>{{ path.evidence }}</small>
                </div>
              </div>
            </el-tab-pane>
            <el-tab-pane label="历史参考">
              <el-card v-for="item in historyReferences" :key="item.fault" shadow="never" class="history-card">
                <strong>{{ item.device_model }} · {{ item.alarm_code }}</strong>
                <p>{{ item.fault }}</p>
                <p>原因：{{ item.reason }}</p>
                <p>处理：{{ item.solution }}</p>
                <el-tag type="success">{{ item.status }}</el-tag>
              </el-card>
              <el-empty v-if="!historyReferences.length" description="暂无历史参考" />
            </el-tab-pane>
            <el-tab-pane label="提交修正">
              <div class="form-stack">
                <el-input v-model="correction.inaccurate" placeholder="AI回答哪里不准确" />
                <el-input v-model="correction.actualReason" placeholder="现场实际原因" />
                <el-input v-model="correction.actualSolution" placeholder="实际处理方式" />
                <el-input v-model="correction.experience" type="textarea" :rows="4" resize="none" placeholder="补充经验" />
                <el-select v-model="correction.type">
                  <el-option label="报警解释错误" value="报警解释错误" />
                  <el-option label="参数检查遗漏" value="参数检查遗漏" />
                  <el-option label="步骤顺序错误" value="步骤顺序错误" />
                  <el-option label="安全提醒缺失" value="安全提醒缺失" />
                  <el-option label="型号匹配错误" value="型号匹配错误" />
                  <el-option label="现场经验补充" value="现场经验补充" />
                </el-select>
                <el-button type="primary" color="#1d4ed8" :loading="submitting" @click="submitWorkbenchCorrection">
                  提交给设备工程师审核
                </el-button>
              </div>
            </el-tab-pane>
          </el-tabs>
        </el-card>
      </aside>
    </div>
    <el-dialog v-model="pagePreviewVisible" :title="pagePreviewTitle" width="72%" class="page-preview-dialog">
      <img v-if="pagePreviewUrl" :src="pagePreviewUrl" class="page-preview-image" alt="维修手册原文页" />
    </el-dialog>
  </section>
</template>

<style scoped>
.workbench-page { gap: 18px; }
.workbench-hero {
  display: flex;
  justify-content: space-between;
  gap: 18px;
  padding: 22px 24px;
  border: 1px solid #1e3a5f;
  border-radius: 10px;
  background: linear-gradient(135deg, #07111f, #10233c);
  color: #fff;
}
.workbench-hero h1 { margin: 6px 0 8px; font-size: 30px; }
.workbench-hero p:last-child { margin: 0; color: #9fb3cc; }
.status-strip { display: flex; flex-wrap: wrap; align-content: flex-start; justify-content: flex-end; gap: 8px; }
.workbench-grid {
  display: grid;
  grid-template-columns: 360px minmax(0, 1fr) 390px;
  gap: 18px;
  align-items: start;
}
.industrial-card {
  border: 1px solid #26364d;
  border-radius: 10px;
  background: #fff;
  box-shadow: 0 12px 26px rgba(15, 23, 42, 0.1);
}
.form-stack { display: flex; flex-direction: column; gap: 12px; }
.hidden-file-input { display: none; }
.image-upload-zone {
  display: flex;
  min-height: 150px;
  width: 100%;
  cursor: pointer;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 10px;
  border: 1px dashed #93c5fd;
  border-radius: 8px;
  background: #f8fbff;
  color: #475569;
  font: inherit;
  text-align: center;
  transition: border-color 0.15s ease, background 0.15s ease;
}
.image-upload-zone:hover { border-color: #2563eb; background: #eff6ff; }
.image-upload-zone .el-icon { color: #2563eb; font-size: 34px; }
.upload-feedback { overflow: hidden; border: 1px solid #bfdbfe; border-radius: 8px; background: #f8fafc; }
.preview { width: 100%; max-height: 180px; object-fit: contain; background: #0f172a; }
.upload-meta { display: flex; align-items: center; justify-content: space-between; gap: 12px; padding: 12px; }
.upload-meta strong { display: block; max-width: 190px; overflow: hidden; color: #111827; text-overflow: ellipsis; white-space: nowrap; }
.upload-meta p { margin: 4px 0 0; color: #64748b; }
.upload-actions { display: flex; flex-wrap: wrap; justify-content: flex-end; gap: 8px; }
.action-row { display: grid; grid-template-columns: 1fr; gap: 10px; }
.result-panel, .assist-panel { display: flex; flex-direction: column; gap: 18px; }
.analysis-grid { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 14px; }
.analysis-grid > .el-alert { grid-column: 1 / -1; }
.alarm-candidate-card {
  grid-column: 1 / -1;
  padding: 14px;
  border: 1px solid #bfdbfe;
  border-radius: 8px;
  background: #f8fafc;
}
.alarm-candidate-head { display: flex; align-items: flex-start; justify-content: space-between; gap: 12px; margin-bottom: 12px; }
.alarm-candidate-head h3 { margin: 0 0 6px; color: #111827; }
.alarm-candidate-head p { margin: 0; color: #64748b; }
.alarm-candidate-list { display: grid; gap: 10px; margin-bottom: 12px; }
.alarm-candidate-item {
  display: flex;
  gap: 10px;
  padding: 12px;
  border: 1px solid #dbeafe;
  border-radius: 8px;
  background: #fff;
  cursor: pointer;
}
.alarm-candidate-body { flex: 1; min-width: 0; }
.alarm-candidate-title { display: flex; flex-wrap: wrap; gap: 8px; align-items: center; color: #111827; }
.alarm-candidate-title strong { font-family: Consolas, monospace; font-size: 16px; }
.alarm-candidate-tags { display: flex; flex-wrap: wrap; gap: 6px; margin: 8px 0; }
.alarm-candidate-body p { margin: 0; color: #64748b; line-height: 1.6; }
.alarm-candidate-actions { display: flex; justify-content: flex-end; margin-top: 10px; }
.confirmed-alarm-summary { display: grid; gap: 12px; }
.confirmed-alarm-summary span { display: block; margin-bottom: 6px; color: #475569; font-weight: 800; }
.confirmed-alarm-summary p { margin: 0; color: #111827; line-height: 1.7; }
.confidence-card {
  grid-column: 1 / -1;
  display: grid;
  gap: 12px;
  padding: 14px;
  border: 1px solid #bfdbfe;
  border-radius: 8px;
  background: #f8fafc;
}
.confidence-head { display: flex; align-items: flex-start; justify-content: space-between; gap: 12px; }
.confidence-head h3 { margin: 0 0 6px; color: #111827; }
.confidence-head p { margin: 0; color: #475569; line-height: 1.6; }
.confidence-metrics { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 8px; }
.confidence-metrics span {
  padding: 8px 10px;
  border: 1px solid #dbeafe;
  border-radius: 6px;
  background: #fff;
  color: #334155;
  font-size: 13px;
}
.result-block { padding: 14px; border: 1px solid #dbeafe; border-radius: 8px; background: #f8fafc; }
.tool-trace-block { grid-column: 1 / -1; }
.tool-trace-list { display: grid; gap: 8px; }
.tool-trace-item { display: flex; justify-content: space-between; gap: 12px; padding: 10px; border: 1px solid #dbeafe; border-radius: 8px; background: #fff; }
.tool-trace-item p { margin: 4px 0; color: #475569; }
.tool-trace-item small { color: #dc2626; }
.tool-trace-meta { display: grid; justify-items: end; gap: 6px; color: #64748b; white-space: nowrap; }
.result-block.risk { border-color: #fed7aa; background: #fff7ed; }
.result-block h3 { margin: 0 0 10px; color: #111827; }
.result-block p { margin: 8px 0 0; color: #334155; line-height: 1.7; }
.workflow-title-row { display: flex; align-items: center; justify-content: space-between; gap: 12px; }
.workflow-title-row h2 { margin: 0 0 12px; font-size: 22px; }
.tool-row, .score-row { display: flex; flex-wrap: wrap; gap: 8px; margin-bottom: 12px; }
.sop-step { padding: 14px; border: 1px solid #dbe2ea; border-radius: 8px; background: #f8fafc; }
.sop-step h3 { margin: 0 0 8px; }
.sop-step p { color: #334155; line-height: 1.75; }
.step-foot { display: flex; justify-content: space-between; gap: 12px; margin-top: 10px; color: #64748b; }
.evidence-title { min-width: 0; flex: 1; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; font-weight: 800; }
.evidence-card { padding: 12px; border: 1px solid #dbeafe; border-radius: 8px; background: #f8fafc; }
.evidence-thumb { width: 100%; max-height: 180px; object-fit: contain; margin: 10px 0; border: 1px solid #dbeafe; border-radius: 8px; background: #fff; }
.evidence-actions { display: flex; flex-wrap: wrap; align-items: center; gap: 8px; margin-top: 10px; }
.page-preview-image { width: 100%; max-height: 78vh; object-fit: contain; background: #f8fafc; }
.filter-alert { margin-bottom: 10px; }
.chunk { color: #64748b; font-family: Consolas, monospace; font-size: 12px; }
.graph-path { display: flex; flex-direction: column; align-items: stretch; gap: 8px; }
.path-node { padding: 12px; border: 1px solid #bfdbfe; border-radius: 8px; background: #eff6ff; color: #1e3a8a; font-weight: 800; }
.path-arrow { color: #2563eb; text-align: center; font-weight: 900; }
.edge-list-mini { display: grid; gap: 8px; margin-top: 12px; }
.edge-mini { display: grid; gap: 6px; padding: 10px; border-radius: 8px; background: #f8fafc; color: #475569; line-height: 1.5; }
.edge-mini small { color: #64748b; }
.history-card { margin-bottom: 10px; border: 1px solid #dbe2ea; }
.history-card p { margin: 8px 0; color: #475569; }
@media (max-width: 1280px) {
  .workbench-grid { grid-template-columns: 1fr; }
  .analysis-grid { grid-template-columns: 1fr; }
}
</style>
