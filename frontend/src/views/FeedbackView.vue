<script setup>
import { ElMessage } from 'element-plus'
import { onMounted, reactive, ref } from 'vue'
import { useRoute } from 'vue-router'

import {
  getFeedbackCases,
  getPendingFeedback,
  reviewFeedback,
  submitFeedback,
} from '../api/feedback'

const route = useRoute()
const activeTab = ref('submit')
const submitting = ref(false)
const loadingPending = ref(false)
const loadingCases = ref(false)
const pendingItems = ref([])
const caseItems = ref([])
const reviewComments = reactive({})

const form = reactive({
  source_type: 'workflow',
  source_id: '',
  original_question: '',
  original_answer: '',
  correction_type: 'answer_fix',
  correction_text: '',
  related_device: '',
  related_fault: '',
  submitter_role: 'worker',
  priority: 'medium',
})

onMounted(() => {
  if (typeof route.query.source_type === 'string') {
    form.source_type = route.query.source_type
  }
  if (typeof route.query.question === 'string') {
    form.original_question = route.query.question
  }
  loadPending()
  loadCases()
})

const handleSubmit = async () => {
  if (!form.correction_text.trim()) {
    ElMessage.warning('请输入修正内容')
    return
  }

  submitting.value = true
  try {
    await submitFeedback({ ...form })
    ElMessage.success('修正已提交，等待专家审核')
    form.correction_text = ''
    activeTab.value = 'review'
    await loadPending()
  } catch (error) {
    ElMessage.error('反馈提交失败，请检查后端服务')
  } finally {
    submitting.value = false
  }
}

const loadPending = async () => {
  loadingPending.value = true
  try {
    const data = await getPendingFeedback()
    pendingItems.value = Array.isArray(data.items) ? data.items : []
  } catch (error) {
    ElMessage.error('待审核列表加载失败')
  } finally {
    loadingPending.value = false
  }
}

const loadCases = async () => {
  loadingCases.value = true
  try {
    const data = await getFeedbackCases()
    caseItems.value = Array.isArray(data.items) ? data.items : []
  } catch (error) {
    ElMessage.error('入库案例加载失败')
  } finally {
    loadingCases.value = false
  }
}

const handleReview = async (item, action) => {
  try {
    await reviewFeedback({
      feedback_id: item.feedback_id,
      action,
      review_comment: reviewComments[item.feedback_id] || '',
      reviewer: 'expert',
    })
    ElMessage.success(action === 'approve' ? '已审核通过并入库' : '已驳回')
    await loadPending()
    await loadCases()
  } catch (error) {
    ElMessage.error('反馈审核失败')
  }
}

const tagType = (value) => {
  if (value === 'high' || value === 'rejected') return 'danger'
  if (value === 'medium' || value === 'pending') return 'warning'
  if (value === 'approved') return 'success'
  return 'info'
}
</script>

<template>
  <section class="page feedback-page">
    <el-card shadow="never" class="feedback-hero">
      <h1>知识沉淀与人工修正闭环</h1>
      <p>用户提交修正内容，经专家审核后进入知识库，用于后续检索、作业卡生成和知识图谱扩展。</p>
    </el-card>

    <el-card shadow="never" class="feedback-panel">
      <el-tabs v-model="activeTab">
        <el-tab-pane label="提交修正" name="submit">
          <el-form label-position="top" class="feedback-form">
            <div class="form-grid">
              <el-form-item label="来源类型">
                <el-select v-model="form.source_type">
                  <el-option label="chat" value="chat" />
                  <el-option label="workflow" value="workflow" />
                  <el-option label="diagnosis" value="diagnosis" />
                </el-select>
              </el-form-item>
              <el-form-item label="修正类型">
                <el-select v-model="form.correction_type">
                  <el-option label="answer_fix" value="answer_fix" />
                  <el-option label="step_add" value="step_add" />
                  <el-option label="safety_add" value="safety_add" />
                  <el-option label="tool_add" value="tool_add" />
                  <el-option label="risk_add" value="risk_add" />
                  <el-option label="other" value="other" />
                </el-select>
              </el-form-item>
              <el-form-item label="优先级">
                <el-select v-model="form.priority">
                  <el-option label="low" value="low" />
                  <el-option label="medium" value="medium" />
                  <el-option label="high" value="high" />
                </el-select>
              </el-form-item>
            </div>

            <el-form-item label="原始问题或任务">
              <el-input v-model="form.original_question" />
            </el-form-item>
            <el-form-item label="AI原始回答或作业卡摘要">
              <el-input v-model="form.original_answer" type="textarea" :rows="3" />
            </el-form-item>
            <el-form-item label="用户修正内容">
              <el-input v-model="form.correction_text" type="textarea" :rows="5" />
            </el-form-item>

            <div class="form-grid">
              <el-form-item label="设备型号">
                <el-input v-model="form.related_device" />
              </el-form-item>
              <el-form-item label="故障现象">
                <el-input v-model="form.related_fault" />
              </el-form-item>
            </div>

            <el-button type="primary" color="#111827" :loading="submitting" @click="handleSubmit">
              提交修正
            </el-button>
          </el-form>
        </el-tab-pane>

        <el-tab-pane label="专家审核" name="review">
          <el-button class="refresh-button" @click="loadPending">刷新待审核</el-button>
          <div v-loading="loadingPending" class="feedback-list">
            <el-empty v-if="!pendingItems.length" description="暂无待审核反馈" />
            <el-card v-for="item in pendingItems" :key="item.feedback_id" shadow="never" class="feedback-item">
              <div class="item-head">
                <div>
                  <el-tag type="warning">pending</el-tag>
                  <el-tag>{{ item.source_type }}</el-tag>
                  <el-tag :type="tagType(item.priority)">{{ item.priority }}</el-tag>
                </div>
                <span>{{ item.created_at }}</span>
              </div>
              <h3>{{ item.original_question || '未填写原始问题' }}</h3>
              <p><strong>修正类型：</strong>{{ item.correction_type }}</p>
              <p><strong>修正内容：</strong>{{ item.correction_text }}</p>
              <p><strong>设备：</strong>{{ item.related_device || '-' }}；<strong>故障：</strong>{{ item.related_fault || '-' }}</p>
              <el-input
                v-model="reviewComments[item.feedback_id]"
                type="textarea"
                :rows="2"
                placeholder="审核意见"
              />
              <div class="review-actions">
                <el-button type="success" @click="handleReview(item, 'approve')">通过</el-button>
                <el-button type="danger" plain @click="handleReview(item, 'reject')">驳回</el-button>
              </div>
            </el-card>
          </div>
        </el-tab-pane>

        <el-tab-pane label="已入库案例" name="cases">
          <el-button class="refresh-button" @click="loadCases">刷新案例</el-button>
          <div v-loading="loadingCases" class="case-list">
            <el-empty v-if="!caseItems.length" description="暂无已入库案例" />
            <el-card v-for="item in caseItems" :key="item.case_id" shadow="never" class="case-item">
              <div class="item-head">
                <strong>{{ item.case_id }}</strong>
                <el-tag type="success">{{ item.status }}</el-tag>
              </div>
              <h3>{{ item.title }}</h3>
              <p><strong>设备：</strong>{{ item.device || '-' }}；<strong>故障：</strong>{{ item.fault || '-' }}</p>
              <p>{{ item.correction_text }}</p>
              <div class="keyword-row">
                <el-tag v-for="keyword in item.keywords" :key="keyword" effect="plain">{{ keyword }}</el-tag>
              </div>
              <div class="case-time">{{ item.created_at }}</div>
            </el-card>
          </div>
        </el-tab-pane>
      </el-tabs>
    </el-card>
  </section>
</template>

<style scoped>
.feedback-hero,
.feedback-panel,
.feedback-item,
.case-item {
  border: 1px solid #dbe2ea;
  border-radius: 10px;
  box-shadow: 0 8px 22px rgba(15, 23, 42, 0.08);
}

.feedback-hero {
  background: #111827;
  color: #ffffff;
}

.feedback-hero h1 {
  margin: 0 0 10px;
  font-size: 28px;
}

.feedback-hero p {
  margin: 0;
  color: #aeb8c8;
}

.feedback-form,
.feedback-list,
.case-list {
  display: flex;
  flex-direction: column;
  gap: 14px;
}

.form-grid {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 12px;
}

.refresh-button {
  align-self: flex-start;
  margin-bottom: 12px;
}

.item-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  color: #64748b;
}

.item-head > div,
.keyword-row {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
}

.feedback-item h3,
.case-item h3 {
  margin: 14px 0 10px;
  color: #111827;
}

.feedback-item p,
.case-item p {
  color: #334155;
  line-height: 1.7;
}

.review-actions {
  display: flex;
  justify-content: flex-end;
  gap: 10px;
  margin-top: 12px;
}

.case-time {
  margin-top: 10px;
  color: #64748b;
  font-size: 13px;
}

@media (max-width: 980px) {
  .form-grid {
    grid-template-columns: 1fr;
  }
}
</style>
