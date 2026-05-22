<script setup>
import { Document, Upload, UploadFilled } from '@element-plus/icons-vue'
import { ElMessage } from 'element-plus'
import { computed, ref } from 'vue'

import { uploadManual } from '../api/manual'

const MAX_FILE_SIZE = 50 * 1024 * 1024

const uploadRef = ref(null)
const fileList = ref([])
const uploadedManuals = ref([])
const uploading = ref(false)
const activeUploadCount = ref(0)

const hasReadyFiles = computed(() => {
  return fileList.value.some((file) => file.status === 'ready')
})

const isPdfFile = (file) => {
  return file.type === 'application/pdf' || file.name.toLowerCase().endsWith('.pdf')
}

const validateFile = (file) => {
  if (!isPdfFile(file)) {
    ElMessage.error('文件格式错误：只能上传 PDF 文件')
    return false
  }

  if (file.size > MAX_FILE_SIZE) {
    ElMessage.error('文件大小不能超过 50MB')
    return false
  }

  return true
}

const handleChange = (uploadFile, uploadFiles) => {
  const rawFile = uploadFile.raw
  if (rawFile && !validateFile(rawFile)) {
    fileList.value = uploadFiles.filter((file) => file.uid !== uploadFile.uid)
    return
  }

  fileList.value = uploadFiles
}

const handleRemove = (_uploadFile, uploadFiles) => {
  fileList.value = uploadFiles
}

const submitUpload = () => {
  if (!fileList.value.length) {
    ElMessage.warning('请先选择 PDF 文件')
    return
  }

  if (!hasReadyFiles.value) {
    ElMessage.info('没有待上传的文件')
    return
  }

  uploadRef.value?.submit()
}

const uploadRequest = async (options) => {
  activeUploadCount.value += 1
  uploading.value = true

  try {
    const result = await uploadManual(options.file, (event) => {
      const percent = event.total ? Math.round((event.loaded * 100) / event.total) : 0
      options.onProgress({ percent })
    })

    if (!result.success) {
      throw new Error(result.error || '上传失败')
    }

    const record = {
      filename: result.filename,
      originalName: options.file.name,
      uploadedAt: new Date().toLocaleString(),
    }
    uploadedManuals.value.unshift(record)

    ElMessage.success(`${result.filename} 上传成功，知识库已更新`)
    options.onSuccess(result)
  } catch (error) {
    const message = error?.response ? error.message || '上传失败' : '网络错误，后端服务连接失败'
    ElMessage.error(message)
    options.onError(error)
  } finally {
    activeUploadCount.value -= 1
    uploading.value = activeUploadCount.value > 0
  }
}
</script>

<template>
  <section class="page">
    <div class="page-header">
      <div>
        <p class="eyebrow">Manual Upload</p>
        <h1>PDF上传</h1>
      </div>
      <el-tag type="success">已接后端</el-tag>
    </div>

    <div class="upload-grid">
      <el-card shadow="never" class="upload-panel upload-card">
        <template #header>
          <div class="upload-card-header">
            <span>上传维修手册</span>
            <el-tag type="info">PDF · 50MB以内</el-tag>
          </div>
        </template>

        <el-upload
          ref="uploadRef"
          v-model:file-list="fileList"
          drag
          action="#"
          :auto-upload="false"
          :http-request="uploadRequest"
          :on-change="handleChange"
          :on-remove="handleRemove"
          accept=".pdf,application/pdf"
          multiple
        >
          <el-icon class="el-icon--upload"><UploadFilled /></el-icon>
          <div class="el-upload__text">
            拖拽 PDF 到此处，或 <em>点击选择文件</em>
          </div>
          <template #tip>
            <div class="el-upload__tip">
              仅支持 PDF 文件，单个文件大小不超过 50MB。点击下方按钮后上传到知识库。
            </div>
          </template>
        </el-upload>

        <div class="upload-actions">
          <el-button
            type="primary"
            color="#111827"
            :icon="Upload"
            :loading="uploading"
            :disabled="!hasReadyFiles"
            @click="submitUpload"
          >
            点击上传
          </el-button>
        </div>

        <div class="selected-files">
          <div class="section-title">文件列表</div>
          <el-empty v-if="!fileList.length" description="暂无待上传文件" :image-size="88" />
          <div v-else class="file-list">
            <div v-for="file in fileList" :key="file.uid" class="file-row">
              <div class="file-main">
                <el-icon><Document /></el-icon>
                <div>
                  <div class="file-name">{{ file.name }}</div>
                  <div class="file-status">
                    {{ file.status === 'success' ? '上传成功 · 知识库已更新' : '等待上传' }}
                  </div>
                </div>
              </div>
              <el-progress
                :percentage="Math.round(file.percentage || 0)"
                :status="file.status === 'success' ? 'success' : undefined"
              />
            </div>
          </div>
        </div>
      </el-card>

      <el-card shadow="never" class="uploaded-card">
        <template #header>
          <div class="upload-card-header">
            <span>已上传知识文档</span>
            <el-tag>{{ uploadedManuals.length }} 个文件</el-tag>
          </div>
        </template>

        <el-empty
          v-if="!uploadedManuals.length"
          description="上传成功后将在这里显示"
          :image-size="96"
        />
        <div v-else class="manual-list">
          <div
            v-for="manual in uploadedManuals"
            :key="`${manual.filename}-${manual.uploadedAt}`"
            class="manual-item"
          >
            <div class="manual-icon">
              <el-icon><Document /></el-icon>
            </div>
            <div class="manual-content">
              <div class="manual-name">{{ manual.filename }}</div>
              <div class="manual-meta">原文件：{{ manual.originalName }}</div>
              <div class="manual-meta">{{ manual.uploadedAt }} · 知识库已更新</div>
            </div>
          </div>
        </div>
      </el-card>
    </div>
  </section>
</template>

<style scoped>
.upload-grid {
  display: grid;
  grid-template-columns: minmax(0, 1.4fr) minmax(320px, 0.8fr);
  gap: 18px;
  align-items: start;
}

.upload-card,
.uploaded-card {
  border: 1px solid #dbe2ea;
  border-radius: 8px;
}

.upload-card-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  font-weight: 800;
}

.upload-actions {
  display: flex;
  justify-content: flex-end;
  margin-top: 16px;
  padding-bottom: 16px;
  border-bottom: 1px solid #e5e7eb;
}

.selected-files {
  margin-top: 16px;
}

.section-title {
  margin-bottom: 12px;
  color: #172033;
  font-size: 15px;
  font-weight: 800;
}

.file-list,
.manual-list {
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.file-row,
.manual-item {
  padding: 14px;
  border: 1px solid #dbe2ea;
  border-radius: 8px;
  background: #f8fafc;
}

.file-main,
.manual-item {
  display: flex;
  gap: 12px;
}

.file-main {
  align-items: center;
  margin-bottom: 10px;
}

.file-name,
.manual-name {
  color: #172033;
  font-weight: 800;
}

.file-status,
.manual-meta {
  margin-top: 4px;
  color: #64748b;
  font-size: 13px;
}

.manual-icon {
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

.manual-content {
  min-width: 0;
}

@media (max-width: 980px) {
  .upload-grid {
    grid-template-columns: 1fr;
  }
}
</style>
