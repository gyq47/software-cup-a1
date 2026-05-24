<template>
  <section class="page">
    <div class="page-header">
      <div>
        <p class="eyebrow">Knowledge Graph</p>
        <h1>知识图谱</h1>
      </div>
      <el-tag type="info">后续扩展模块</el-tag>
    </div>

    <el-card shadow="never" class="placeholder-card">
      <h2>后续扩展模块</h2>
      <div class="placeholder-grid">
        <div>知识图谱</div>
        <div>图谱检索</div>
        <div>图谱更新</div>
        <div>案例关系追踪</div>
      </div>
    </el-card>
  </section>
</template>

<style scoped>
.placeholder-card {
  border: 1px solid #dbe2ea;
  border-radius: 10px;
}

.placeholder-grid {
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: 12px;
}

.placeholder-grid div {
  padding: 16px;
  border-radius: 8px;
  background: #f8fafc;
  font-weight: 800;
}
</style>
