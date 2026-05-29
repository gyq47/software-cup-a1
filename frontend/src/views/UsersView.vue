<template>
  <section class="page admin-page">
    <div class="admin-hero">
      <p class="eyebrow">User Administration</p>
      <h1>用户管理</h1>
      <p>演示系统采用管理员统一分配账号，当前展示固定角色与权限边界。</p>
    </div>
    <el-card shadow="never" class="admin-card">
      <el-table :data="users" stripe>
        <el-table-column prop="username" label="用户名" />
        <el-table-column prop="display" label="显示名称" />
        <el-table-column prop="role" label="角色" />
        <el-table-column prop="scope" label="权限范围" min-width="260" />
      </el-table>
    </el-card>
  </section>
</template>

<script setup>
const users = [
  { username: 'worker', display: '检修人员', role: 'worker', scope: '工作台、我的检修记录、提交修正' },
  { username: 'expert', display: '设备工程师', role: 'expert', scope: '工作台、知识审核与沉淀、手册管理' },
  { username: 'admin', display: '系统管理员', role: 'admin', scope: '工作台、手册管理、用户管理、系统配置、系统诊断' },
]
</script>

<style scoped>
.admin-hero { padding: 22px 24px; border-radius: 10px; background: #111827; color: #fff; }
.admin-hero h1 { margin: 6px 0 8px; font-size: 30px; }
.admin-hero p:last-child { margin: 0; color: #aeb8c8; }
.admin-card { border: 1px solid #dbe2ea; border-radius: 10px; }
</style>
