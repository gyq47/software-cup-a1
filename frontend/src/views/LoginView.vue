<script setup>
import { Connection, Lock, RefreshRight, User } from '@element-plus/icons-vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { onMounted, reactive, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'

import { useAuthStore } from '../stores/auth'

const route = useRoute()
const router = useRouter()
const auth = useAuthStore()
const loading = ref(false)
const captchaCode = ref('')

const form = reactive({
  username: 'worker',
  password: '123456',
  role: 'worker',
  captcha: '',
})

const roleOptions = [
  { label: '检修人员（worker）', value: 'worker' },
  { label: '设备工程师（expert）', value: 'expert' },
  { label: '系统管理员（admin）', value: 'admin' },
]

const refreshCaptcha = () => {
  const chars = 'ABCDEFGHJKLMNPQRSTUVWXYZ23456789'
  captchaCode.value = Array.from({ length: 4 }, () => chars[Math.floor(Math.random() * chars.length)]).join('')
  form.captcha = ''
}

const handleForgotPassword = () => {
  ElMessageBox.alert('请联系系统管理员重置密码。', '忘记密码', {
    confirmButtonText: '知道了',
    type: 'info',
  })
}

const handleLogin = async () => {
  if (form.captcha.trim().toUpperCase() !== captchaCode.value) {
    ElMessage.error('图形验证码错误')
    refreshCaptcha()
    return
  }

  loading.value = true
  try {
    await auth.login(form.username, form.password, form.role)
    ElMessage.success('登录成功')
    router.push(typeof route.query.redirect === 'string' ? route.query.redirect : '/')
  } catch (error) {
    ElMessage.error(error.message || '用户名、密码或角色不匹配')
    refreshCaptcha()
  } finally {
    loading.value = false
  }
}

onMounted(() => {
  refreshCaptcha()
})
</script>

<template>
  <section class="login-page industrial-login">
    <div class="login-shell">
      <div class="login-brand">
        <div class="login-logo">
          <el-icon><Connection /></el-icon>
        </div>
        <h1>设备检修智能平台</h1>
        <p>Industrial Knowledge Ops Platform</p>
      </div>

      <div class="login-layout">
        <el-card shadow="never" class="login-card">
          <template #header>
            <div class="login-card-header">
              <span>内部账号登录</span>
              <el-tag type="info" effect="dark">RBAC</el-tag>
            </div>
          </template>

          <el-form label-position="top">
            <el-form-item label="用户名">
              <el-input v-model="form.username" size="large" :prefix-icon="User" placeholder="worker / expert / admin" />
            </el-form-item>
            <el-form-item label="密码">
              <el-input
                v-model="form.password"
                size="large"
                type="password"
                show-password
                :prefix-icon="Lock"
                placeholder="请输入管理员分配的密码"
              />
            </el-form-item>
            <el-form-item label="角色">
              <el-select v-model="form.role" size="large">
                <el-option
                  v-for="item in roleOptions"
                  :key="item.value"
                  :label="item.label"
                  :value="item.value"
                />
              </el-select>
            </el-form-item>
            <el-form-item label="图形验证码">
              <div class="captcha-row">
                <el-input
                  v-model="form.captcha"
                  size="large"
                  placeholder="输入右侧验证码"
                  @keydown.enter="handleLogin"
                />
                <button type="button" class="captcha-box" @click="refreshCaptcha">
                  {{ captchaCode }}
                  <el-icon><RefreshRight /></el-icon>
                </button>
              </div>
            </el-form-item>

            <div class="login-actions">
              <el-button link type="primary" @click="handleForgotPassword">忘记密码</el-button>
              <span>账号由系统管理员统一分配</span>
            </div>

            <el-button type="primary" color="#1d4ed8" size="large" :loading="loading" @click="handleLogin">
              登录
            </el-button>
          </el-form>
        </el-card>

        <div class="role-panel">
          <el-card shadow="never">
            <strong>worker · 检修人员</strong>
            <p>现场检修、故障诊断、作业执行、提交修正。</p>
          </el-card>
          <el-card shadow="never">
            <strong>expert · 设备工程师</strong>
            <p>知识审核、经验沉淀、案例审核、查看知识图谱。</p>
          </el-card>
          <el-card shadow="never">
            <strong>admin · 系统管理员</strong>
            <p>系统配置、规则管理、模型管理、用户管理展示。</p>
          </el-card>
        </div>
      </div>
    </div>
  </section>
</template>

<style scoped>
.industrial-login {
  position: relative;
  overflow: hidden;
  background:
    linear-gradient(135deg, rgba(15, 23, 42, 0.94), rgba(30, 64, 175, 0.76)),
    #0f172a;
}

.industrial-login::before {
  position: absolute;
  inset: 0;
  content: "";
  background-image:
    linear-gradient(rgba(148, 163, 184, 0.11) 1px, transparent 1px),
    linear-gradient(90deg, rgba(148, 163, 184, 0.11) 1px, transparent 1px);
  background-size: 42px 42px;
}

.login-shell {
  position: relative;
  z-index: 1;
  width: min(1120px, 100%);
}

.login-layout {
  display: grid;
  grid-template-columns: minmax(360px, 440px) minmax(0, 1fr);
  gap: 20px;
  align-items: stretch;
}

.login-brand {
  margin-bottom: 24px;
  color: #ffffff;
  text-align: left;
}

.login-logo {
  display: inline-flex;
  width: 58px;
  height: 58px;
  align-items: center;
  justify-content: center;
  border: 1px solid #60a5fa;
  border-radius: 10px;
  background: #1d4ed8;
  font-size: 26px;
}

.login-brand h1 {
  margin: 18px 0 8px;
  font-size: 34px;
}

.login-brand p {
  margin: 0;
  color: #bfdbfe;
}

.login-card,
.role-panel :deep(.el-card) {
  border: 1px solid rgba(147, 197, 253, 0.34);
  border-radius: 10px;
  background: rgba(15, 23, 42, 0.9);
  color: #ffffff;
}

.login-card :deep(.el-card__header) {
  border-bottom-color: rgba(147, 197, 253, 0.22);
}

.login-card-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  font-weight: 800;
}

.login-card :deep(.el-form-item__label) {
  color: #cbd5e1;
}

.login-card .el-button:not(.el-button--text) {
  width: 100%;
}

.captcha-row {
  display: grid;
  width: 100%;
  grid-template-columns: minmax(0, 1fr) 132px;
  gap: 10px;
}

.captcha-box {
  display: flex;
  height: 40px;
  align-items: center;
  justify-content: center;
  gap: 8px;
  border: 1px solid #60a5fa;
  border-radius: 8px;
  background: #0f172a;
  color: #bfdbfe;
  font-family: "SFMono-Regular", Consolas, monospace;
  font-size: 18px;
  font-weight: 900;
  cursor: pointer;
}

.login-actions {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin: -4px 0 16px;
  color: #94a3b8;
  font-size: 13px;
}

.role-panel {
  display: grid;
  gap: 14px;
}

.role-panel strong {
  color: #dbeafe;
}

.role-panel p {
  margin: 8px 0 0;
  color: #94a3b8;
  line-height: 1.7;
}

@media (max-width: 860px) {
  .login-layout {
    grid-template-columns: 1fr;
  }
}
</style>
