<template>
  <section class="page">
    <div class="page-header">
      <div>
        <p class="eyebrow">Admin Console</p>
        <h1>系统管理</h1>
      </div>
      <el-tag type="warning">后续扩展模块</el-tag>
    </div>

    <el-card shadow="never" class="placeholder-card">
      <h2>后续扩展模块</h2>
      <div class="placeholder-grid">
        <div>规则管理</div>
        <div>模型模式切换</div>
        <div>系统状态</div>
        <div>用户管理</div>
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
