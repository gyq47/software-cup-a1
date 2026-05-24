<script setup>
import { Lock, User } from '@element-plus/icons-vue'
import { ElMessage } from 'element-plus'
import { reactive, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'

import { useAuthStore } from '../stores/auth'

const route = useRoute()
const router = useRouter()
const auth = useAuthStore()
const loading = ref(false)
const form = reactive({
  username: 'worker',
  password: '123456',
})

const handleLogin = async () => {
  loading.value = true
  try {
    await auth.login(form.username, form.password)
    ElMessage.success('登录成功')
    router.push(typeof route.query.redirect === 'string' ? route.query.redirect : '/')
  } catch (error) {
    ElMessage.error(error.message || '用户名或密码错误')
  } finally {
    loading.value = false
  }
}
</script>

<template>
  <section class="login-page">
    <div class="login-shell">
      <div class="login-brand">
        <div class="login-logo">A1</div>
        <h1>工业设备检修知识与作业系统</h1>
        <p>Industrial Maintenance Knowledge & Workflow System</p>
      </div>

      <el-card shadow="never" class="login-card">
        <el-form label-position="top">
          <el-form-item label="用户名">
            <el-input v-model="form.username" size="large" :prefix-icon="User" />
          </el-form-item>
          <el-form-item label="密码">
            <el-input
              v-model="form.password"
              size="large"
              type="password"
              show-password
              :prefix-icon="Lock"
              @keydown.enter="handleLogin"
            />
          </el-form-item>
          <el-button type="primary" color="#111827" size="large" :loading="loading" @click="handleLogin">
            登录系统
          </el-button>
        </el-form>
      </el-card>

      <div class="role-grid">
        <el-card shadow="never">
          <strong>worker</strong>
          <p>现场检修、故障诊断、作业执行</p>
        </el-card>
        <el-card shadow="never">
          <strong>expert</strong>
          <p>知识审核、经验沉淀、案例审核</p>
        </el-card>
        <el-card shadow="never">
          <strong>admin</strong>
          <p>系统配置、规则管理、模型管理</p>
        </el-card>
      </div>
    </div>
  </section>
</template>

<style scoped>
.login-page {
  display: flex;
  min-height: 100vh;
  align-items: center;
  justify-content: center;
  padding: 32px;
  background: #0f172a;
}

.login-shell {
  width: min(1040px, 100%);
}

.login-brand {
  margin-bottom: 24px;
  color: #ffffff;
  text-align: center;
}

.login-logo {
  display: inline-flex;
  width: 56px;
  height: 56px;
  align-items: center;
  justify-content: center;
  border-radius: 10px;
  background: #1d4ed8;
  font-weight: 900;
}

.login-brand h1 {
  margin: 18px 0 8px;
  font-size: 32px;
}

.login-brand p {
  margin: 0;
  color: #aeb8c8;
}

.login-card {
  width: min(420px, 100%);
  margin: 0 auto 18px;
  border: 1px solid #334155;
  border-radius: 10px;
}

.login-card .el-button {
  width: 100%;
}

.role-grid {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 14px;
}

.role-grid :deep(.el-card) {
  border: 1px solid #334155;
  background: #111827;
  color: #ffffff;
}

.role-grid p {
  margin: 8px 0 0;
  color: #aeb8c8;
}

@media (max-width: 760px) {
  .role-grid {
    grid-template-columns: 1fr;
  }
}
</style>
