<template>
  <section class="page">
    <div class="page-header">
      <div>
        <p class="eyebrow">Dashboard</p>
        <h1>首页</h1>
      </div>
      <el-tag type="info">基础工程已就绪</el-tag>
    </div>

    <div class="metric-grid">
      <el-card shadow="never" class="metric-card">
        <div class="metric-label">知识库状态</div>
        <div class="metric-value">待接入</div>
        <div class="metric-note">PDF 上传后可用于检索</div>
      </el-card>
      <el-card shadow="never" class="metric-card">
        <div class="metric-label">检索模式</div>
        <div class="metric-value">关键词 / 语义</div>
        <div class="metric-note">支持设备检修知识查询</div>
      </el-card>
      <el-card shadow="never" class="metric-card">
        <div class="metric-label">AI 助手</div>
        <div class="metric-value">RAG 问答</div>
        <div class="metric-note">面向检修作业场景</div>
      </el-card>
    </div>

    <el-card shadow="never" class="work-panel">
      <template #header>
        <div class="card-header">工作台概览</div>
      </template>
      <div class="flow-list">
        <div class="flow-item">
          <span class="flow-index">01</span>
          <div>
            <strong>上传维修手册</strong>
            <p>导入 PDF 文档，为检索和问答提供知识来源。</p>
          </div>
        </div>
        <div class="flow-item">
          <span class="flow-index">02</span>
          <div>
            <strong>检索知识片段</strong>
            <p>通过关键词或语义检索定位相关页码和内容。</p>
          </div>
        </div>
        <div class="flow-item">
          <span class="flow-index">03</span>
          <div>
            <strong>生成检修建议</strong>
            <p>结合检索上下文输出原因、步骤、安全提醒和依据。</p>
          </div>
        </div>
      </div>
    </el-card>
  </section>
</template>
