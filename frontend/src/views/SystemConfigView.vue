<template>
  <section class="page system-page">
    <div class="system-hero">
      <p class="eyebrow">System Configuration</p>
      <h1>系统配置</h1>
      <p>集中展示模型配置、API 配置、RAG 后端和运行模式，不暴露完整密钥。</p>
    </div>
    <div class="config-grid">
      <el-card v-for="item in configs" :key="item.title" shadow="never" class="config-card">
        <h3>{{ item.title }}</h3>
        <p>{{ item.desc }}</p>
        <el-tag :type="item.type">{{ item.status }}</el-tag>
      </el-card>
    </div>
  </section>
</template>

<script setup>
const configs = [
  { title: '模型配置', desc: 'Qwen OpenAI-compatible API，密钥由后端 .env 管理。', status: '已配置', type: 'success' },
  { title: 'RAG 后端', desc: 'LangChain Retriever 优先，旧 Hybrid Search 兜底。', status: 'LangChain', type: 'primary' },
  { title: '向量库', desc: 'Chroma 持久化目录 backend/data/vector_store/chroma。', status: '本地模式', type: 'info' },
  { title: '视觉增强', desc: '增强模式由检修人员在工作台手动开启。', status: '手动启用', type: 'warning' },
]
</script>

<style scoped>
.system-hero { padding: 22px 24px; border-radius: 10px; background: #111827; color: #fff; }
.system-hero h1 { margin: 6px 0 8px; font-size: 30px; }
.system-hero p:last-child { margin: 0; color: #aeb8c8; }
.config-grid { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 16px; }
.config-card { border: 1px solid #dbe2ea; border-radius: 10px; }
.config-card h3 { margin: 0 0 8px; color: #111827; }
.config-card p { color: #475569; line-height: 1.8; }
@media (max-width: 900px) { .config-grid { grid-template-columns: 1fr; } }
</style>
