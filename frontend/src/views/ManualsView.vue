<script setup>
import { ElMessage } from 'element-plus'
import { onMounted, reactive, ref } from 'vue'

import { getManualList, rebuildManualIndex, reindexManual, uploadManual } from '../api/manual'

const manuals = ref([])
const uploading = ref(false)
const loading = ref(false)
const rebuilding = ref(false)
const reindexingKey = ref('')
const filters = reactive({
  device_model: '',
  manual_type: '',
})
const uploadForm = reactive({
  deviceModel: '808D',
  manualType: 'diagnosis',
})
const deviceOptions = ['808D', '828D', 'common']
const manualTypeOptions = ['diagnosis', 'parameter', 'plc', 'electrical', 'drive', 'operation', 'repair', 'other']
const summary = ref({
  total: 0,
  indexed_count: 0,
  total_chunks: 0,
  vector_store_ready: false,
})

const loadManuals = async () => {
  loading.value = true
  try {
    const data = await getManualList({
      device_model: filters.device_model || undefined,
      manual_type: filters.manual_type || undefined,
    })
    manuals.value = data.items || []
    summary.value = {
      total: data.total || 0,
      indexed_count: data.indexed_count || 0,
      total_chunks: data.total_chunks || 0,
      vector_store_ready: Boolean(data.vector_store_ready),
    }
  } catch (error) {
    ElMessage.error('手册列表获取失败')
  } finally {
    loading.value = false
  }
}

const upload = async (options) => {
  uploading.value = true
  try {
    const data = await uploadManual(options.file, {
      deviceModel: uploadForm.deviceModel,
      manualType: uploadForm.manualType,
    })
    ElMessage.success(data.message || data.index_message || '维修手册已上传并索引')
    await loadManuals()
  } catch (error) {
    ElMessage.error('手册上传失败')
  } finally {
    uploading.value = false
  }
}

const reindex = async (row) => {
  const key = row.relative_path || `${row.source_dir}-${row.filename}`
  reindexingKey.value = key
  try {
    const data = await reindexManual({
      relative_path: row.relative_path,
      filename: row.filename,
      source_dir: row.source_dir,
    })
    ElMessage.success(data.message || '重新索引任务已提交')
    await loadManuals()
  } catch (error) {
    ElMessage.error('单本手册重新索引失败')
  } finally {
    reindexingKey.value = ''
  }
}

const rebuildAll = async () => {
  rebuilding.value = true
  try {
    const data = await rebuildManualIndex()
    ElMessage.success(data.message || '全部手册索引已重建')
    await loadManuals()
  } catch (error) {
    ElMessage.error('一键重建索引失败')
  } finally {
    rebuilding.value = false
  }
}

const formatSize = (size) => {
  const value = Number(size)
  if (!Number.isFinite(value)) return '-'
  if (value >= 1024 * 1024) return `${(value / 1024 / 1024).toFixed(1)} MB`
  if (value >= 1024) return `${(value / 1024).toFixed(1)} KB`
  return `${value} B`
}

const formatTime = (timestamp) => {
  const value = Number(timestamp)
  if (!Number.isFinite(value)) return '-'
  return new Date(value * 1000).toLocaleString()
}

const sourceLabel = (sourceDir) => {
  if (sourceDir === 'static') return '内置手册'
  if (sourceDir === 'upload') return '上传手册'
  return sourceDir || '-'
}

onMounted(loadManuals)
</script>

<template>
  <section class="page manuals-page">
    <div class="manuals-hero">
      <div>
        <p class="eyebrow">Manual Repository</p>
        <h1>手册管理</h1>
        <p>上传、查看和维护维修手册索引状态，供 RAG 检索和作业卡生成使用。</p>
      </div>
    </div>

    <el-card shadow="never" class="manual-card">
      <template #header>上传维修手册</template>
      <div class="upload-options">
        <el-select v-model="uploadForm.deviceModel" placeholder="设备型号">
          <el-option v-for="item in deviceOptions" :key="item" :label="item" :value="item" />
        </el-select>
        <el-select v-model="uploadForm.manualType" placeholder="手册类型">
          <el-option v-for="item in manualTypeOptions" :key="item" :label="item" :value="item" />
        </el-select>
      </div>
      <el-upload drag action="#" accept=".pdf" :http-request="upload" :disabled="uploading">
        <div class="el-upload__text">拖拽 PDF 手册到此处，或点击上传</div>
      </el-upload>
    </el-card>

    <el-card shadow="never" class="manual-card">
      <template #header>
        <div class="manual-header">
          <span>已识别手册</span>
          <div class="manual-actions">
            <el-select v-model="filters.device_model" clearable placeholder="设备型号" style="width: 120px" @change="loadManuals">
              <el-option label="全部" value="" />
              <el-option v-for="item in deviceOptions" :key="item" :label="item" :value="item" />
            </el-select>
            <el-select v-model="filters.manual_type" clearable placeholder="手册类型" style="width: 150px" @change="loadManuals">
              <el-option label="全部" value="" />
              <el-option v-for="item in manualTypeOptions" :key="item" :label="item" :value="item" />
            </el-select>
            <el-tag type="primary">总数 {{ summary.total }}</el-tag>
            <el-tag type="success">已索引 {{ summary.indexed_count }}</el-tag>
            <el-tag type="info">chunks {{ summary.total_chunks }}</el-tag>
            <el-button type="primary" color="#111827" :loading="rebuilding" @click="rebuildAll">
              一键重建索引
            </el-button>
          </div>
        </div>
      </template>
      <el-table v-loading="loading" :data="manuals" stripe>
        <el-table-column prop="filename" label="文件名" min-width="220" />
        <el-table-column prop="relative_path" label="相对路径" min-width="260" />
        <el-table-column prop="device_model" label="设备型号" width="150" />
        <el-table-column prop="manual_type" label="文档类型" width="140" />
        <el-table-column label="来源目录" width="110">
          <template #default="{ row }">
            <el-tag :type="row.source_dir === 'static' ? 'primary' : 'warning'" effect="plain">
              {{ sourceLabel(row.source_dir) }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column label="文件大小" width="110">
          <template #default="{ row }">{{ formatSize(row.file_size) }}</template>
        </el-table-column>
        <el-table-column prop="index_status" label="索引状态" width="120">
          <template #default="{ row }">
            <el-tag :type="row.indexed ? 'success' : 'info'">{{ row.index_status }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="chunk_count" label="chunk数量" width="120" />
        <el-table-column label="更新时间" width="180">
          <template #default="{ row }">{{ formatTime(row.updated_at) }}</template>
        </el-table-column>
        <el-table-column label="操作" width="130" fixed="right">
          <template #default="{ row }">
            <el-button
              size="small"
              :loading="reindexingKey === (row.relative_path || `${row.source_dir}-${row.filename}`)"
              @click="reindex(row)"
            >
              重新索引
            </el-button>
          </template>
        </el-table-column>
      </el-table>
    </el-card>
  </section>
</template>

<style scoped>
.manuals-hero { padding: 22px 24px; border-radius: 10px; background: #111827; color: #fff; }
.manuals-hero h1 { margin: 6px 0 8px; font-size: 30px; }
.manuals-hero p:last-child { margin: 0; color: #aeb8c8; }
.manual-card { border: 1px solid #dbe2ea; border-radius: 10px; }
.upload-options {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 220px));
  gap: 12px;
  margin-bottom: 14px;
}
.manual-header,
.manual-actions {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
}
.manual-actions {
  flex-wrap: wrap;
  justify-content: flex-end;
}
</style>
