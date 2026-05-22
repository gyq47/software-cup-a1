<script setup>
import { UploadFilled } from '@element-plus/icons-vue'

const beforeUpload = (file) => {
  return file.type === 'application/pdf' || file.name.toLowerCase().endsWith('.pdf')
}
</script>

<template>
  <section class="page">
    <div class="page-header">
      <div>
        <p class="eyebrow">Manual Upload</p>
        <h1>PDF上传</h1>
      </div>
      <el-tag type="info">本地占位</el-tag>
    </div>

    <el-card shadow="never" class="upload-panel">
      <el-upload
        drag
        action="#"
        :auto-upload="false"
        :before-upload="beforeUpload"
        accept=".pdf,application/pdf"
      >
        <el-icon class="el-icon--upload"><UploadFilled /></el-icon>
        <div class="el-upload__text">
          拖拽 PDF 到此处，或 <em>点击选择文件</em>
        </div>
        <template #tip>
          <div class="el-upload__tip">当前为前端占位上传区，后续可接入 /api/manual/upload。</div>
        </template>
      </el-upload>
    </el-card>
  </section>
</template>
