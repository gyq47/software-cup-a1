<script setup>
import { Search } from '@element-plus/icons-vue'
import { computed, ref } from 'vue'

const keyword = ref('')
const results = ref([
  {
    title: '发动机启动失败排查',
    file: 'engine_manual.pdf',
    page: 12,
    content: '检查蓄电池电压、启动继电器、燃油供给和安全联锁开关状态。',
  },
  {
    title: '液压系统压力异常',
    file: 'hydraulic_guide.pdf',
    page: 8,
    content: '确认油位、滤芯堵塞情况、泄压阀状态和管路泄漏点。',
  },
  {
    title: '电气柜温度过高',
    file: 'electrical_panel.pdf',
    page: 21,
    content: '检查风扇、滤网、端子接触电阻和柜内负载分布。',
  },
])

const filteredResults = computed(() => {
  const text = keyword.value.trim()
  if (!text) return results.value

  return results.value.filter((item) => {
    return `${item.title}${item.file}${item.content}`.includes(text)
  })
})
</script>

<template>
  <section class="page">
    <div class="page-header">
      <div>
        <p class="eyebrow">Knowledge Search</p>
        <h1>知识检索</h1>
      </div>
      <el-tag type="info">假数据</el-tag>
    </div>

    <el-card shadow="never" class="search-panel">
      <div class="search-bar">
        <el-input
          v-model="keyword"
          size="large"
          placeholder="输入设备名称、故障现象或检修关键词"
          clearable
        />
        <el-button type="primary" size="large" :icon="Search">搜索</el-button>
      </div>

      <div class="result-list">
        <div
          v-for="item in filteredResults"
          :key="`${item.file}-${item.page}`"
          class="result-card"
        >
          <div class="result-title">{{ item.title }}</div>
          <div class="result-meta">{{ item.file }} · 第 {{ item.page }} 页</div>
          <p>{{ item.content }}</p>
        </div>
      </div>
    </el-card>
  </section>
</template>
