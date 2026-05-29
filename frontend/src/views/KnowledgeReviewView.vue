<script setup>
import { ElMessage } from 'element-plus'
import { onMounted, ref } from 'vue'

import { approveReview, getApprovedKnowledge, getPendingReviews, rejectReview } from '../api/review'

const loading = ref(false)
const pendingItems = ref([])
const approvedItems = ref([])
const comments = ref({})

const loadData = async () => {
  loading.value = true
  try {
    pendingItems.value = await getPendingReviews()
    approvedItems.value = await getApprovedKnowledge()
  } catch (error) {
    ElMessage.error('知识审核数据加载失败')
  } finally {
    loading.value = false
  }
}

const approve = async (item) => {
  await approveReview(item.feedback_id, comments.value[item.feedback_id] || '审核通过')
  ElMessage.success('该内容已沉淀为知识案例，将用于后续知识检索、关联分析和标准作业卡生成。')
  await loadData()
}

const reject = async (item) => {
  await rejectReview(item.feedback_id, comments.value[item.feedback_id] || '依据不足，驳回')
  ElMessage.warning('已驳回该修正内容')
  await loadData()
}

onMounted(loadData)
</script>

<template>
  <section class="page review-page">
    <div class="review-hero">
      <div>
        <p class="eyebrow">Knowledge Review</p>
        <h1>知识审核与沉淀</h1>
        <p>设备工程师审核现场修正和经验补充，审核通过后进入知识库。</p>
      </div>
      <el-tag type="warning" effect="dark">仅设备工程师</el-tag>
    </div>

    <el-tabs v-loading="loading" class="review-tabs">
      <el-tab-pane label="待审核">
        <el-empty v-if="!pendingItems.length" description="暂无待审核内容" />
        <el-card v-for="item in pendingItems" :key="item.feedback_id" shadow="never" class="review-card">
          <div class="review-card-head">
            <div>
              <strong>{{ item.related_device || '未标注设备' }}</strong>
              <p>{{ item.original_question }}</p>
            </div>
            <el-tag type="warning">待审核</el-tag>
          </div>
          <div class="review-grid">
            <div><span>提交人</span><strong>{{ item.submitter_role || 'worker' }}</strong></div>
            <div><span>报警代码</span><strong>{{ item.related_fault || '-' }}</strong></div>
            <div><span>标注类型</span><strong>{{ item.correction_type }}</strong></div>
            <div><span>提交时间</span><strong>{{ item.created_at || '-' }}</strong></div>
          </div>
          <el-alert title="用户修正内容" :description="item.correction_text" type="info" :closable="false" />
          <el-input v-model="comments[item.feedback_id]" placeholder="审核意见" class="comment-input" />
          <div class="review-actions">
            <el-button @click="reject(item)">驳回</el-button>
            <el-button type="primary" color="#1d4ed8" @click="approve(item)">通过</el-button>
            <el-button>查看依据</el-button>
          </div>
        </el-card>
      </el-tab-pane>

      <el-tab-pane label="已沉淀知识">
        <el-empty v-if="!approvedItems.length" description="暂无已沉淀知识" />
        <el-card v-for="item in approvedItems" :key="item.case_id" shadow="never" class="review-card">
          <div class="review-card-head">
            <div>
              <strong>{{ item.title || item.case_id }}</strong>
              <p>{{ item.fault || '现场经验知识' }}</p>
            </div>
            <el-tag type="success">已入知识库</el-tag>
          </div>
          <div class="review-grid">
            <div><span>知识ID</span><strong>{{ item.case_id }}</strong></div>
            <div><span>设备型号</span><strong>{{ item.device || '-' }}</strong></div>
            <div><span>审核人</span><strong>expert</strong></div>
            <div><span>审核时间</span><strong>{{ item.created_at || '-' }}</strong></div>
          </div>
          <p class="knowledge-text">{{ item.correction_text }}</p>
          <div class="tag-row">
            <el-tag v-for="keyword in item.keywords" :key="keyword" effect="plain">{{ keyword }}</el-tag>
          </div>
        </el-card>
      </el-tab-pane>
    </el-tabs>
  </section>
</template>

<style scoped>
.review-hero {
  display: flex;
  justify-content: space-between;
  gap: 18px;
  padding: 22px 24px;
  border-radius: 10px;
  background: #111827;
  color: #fff;
}
.review-hero h1 { margin: 6px 0 8px; font-size: 30px; }
.review-hero p:last-child { margin: 0; color: #aeb8c8; }
.review-tabs { padding: 18px; border: 1px solid #dbe2ea; border-radius: 10px; background: #fff; }
.review-card { margin-bottom: 14px; border: 1px solid #dbe2ea; border-radius: 10px; }
.review-card-head { display: flex; justify-content: space-between; gap: 12px; margin-bottom: 12px; }
.review-card-head p { margin: 6px 0 0; color: #64748b; }
.review-grid { display: grid; grid-template-columns: repeat(4, minmax(0, 1fr)); gap: 10px; margin-bottom: 12px; }
.review-grid div { padding: 10px; border-radius: 8px; background: #f8fafc; }
.review-grid span { display: block; margin-bottom: 4px; color: #64748b; font-size: 12px; }
.comment-input { margin-top: 12px; }
.review-actions { display: flex; justify-content: flex-end; gap: 10px; margin-top: 12px; }
.knowledge-text { color: #334155; line-height: 1.8; }
.tag-row { display: flex; flex-wrap: wrap; gap: 8px; }
@media (max-width: 900px) { .review-grid { grid-template-columns: 1fr; } }
</style>
