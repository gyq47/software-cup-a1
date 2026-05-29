<script setup>
import {
  DocumentAdd,
  EditPen,
  Files,
  Share,
  Operation,
  Setting,
  User,
  WarningFilled,
} from '@element-plus/icons-vue'
import { computed } from 'vue'
import { useRoute, useRouter } from 'vue-router'

import { useAuthStore } from '../stores/auth'

const route = useRoute()
const router = useRouter()
const auth = useAuthStore()

const activeMenu = computed(() => route.path)
const roleLabel = computed(() => {
  if (auth.role === 'worker') return '检修人员'
  if (auth.role === 'expert') return '设备工程师'
  if (auth.role === 'admin') return '系统管理员'
  return '未登录'
})

const menuItems = computed(() => {
  const items = [
    { index: '/workbench', label: '工业检修工作台', icon: Operation, roles: ['worker', 'expert', 'admin'] },
    { index: '/my-records', label: '我的检修记录', icon: Files, roles: ['worker'] },
    { index: '/review', label: '知识审核与沉淀', icon: EditPen, roles: ['expert'] },
    { index: '/graph', label: '知识图谱', icon: Share, roles: ['expert', 'admin'] },
    { index: '/manuals', label: '手册管理', icon: DocumentAdd, roles: ['expert', 'admin'] },
    { index: '/users', label: '用户管理', icon: User, roles: ['admin'] },
    { index: '/system', label: '系统配置', icon: Setting, roles: ['admin'] },
    { index: '/diagnostics', label: '系统诊断', icon: WarningFilled, roles: ['admin'] },
  ]
  return items.filter((item) => item.roles.includes(auth.role))
})

const handleSelect = (path) => {
  router.push(path)
}

const handleLogout = async () => {
  await auth.logout()
  router.push('/login')
}
</script>

<template>
  <el-container class="app-shell">
    <el-aside class="sidebar" width="236px">
      <div class="brand">
        <div class="brand-mark">A1</div>
        <div>
          <div class="brand-title">设备检修系统</div>
          <div class="brand-subtitle">Knowledge Ops</div>
        </div>
      </div>

      <el-menu
        :default-active="activeMenu"
        background-color="#111827"
        text-color="#aeb8c8"
        active-text-color="#ffffff"
        class="side-menu"
        @select="handleSelect"
      >
        <el-menu-item v-for="item in menuItems" :key="item.index" :index="item.index">
          <el-icon><component :is="item.icon" /></el-icon>
          <span>{{ item.label }}</span>
        </el-menu-item>
      </el-menu>
    </el-aside>

    <el-container class="main-area">
      <el-header class="topbar">
        <div>
          <div class="system-name">基于多模态大模型技术的设备检修知识检索与作业系统</div>
          <div class="system-status">工业检修工作台 · 知识沉淀 · LangChain RAG · 标准作业指导</div>
        </div>
        <div class="user-area">
          <el-avatar :size="34">{{ auth.display_name?.slice(0, 1) }}</el-avatar>
          <div class="user-meta">
            <strong>{{ auth.display_name }}</strong>
            <el-tag size="small" type="info">{{ roleLabel }}</el-tag>
          </div>
          <el-button size="small" @click="handleLogout">退出登录</el-button>
        </div>
      </el-header>

      <el-main class="content">
        <router-view />
      </el-main>
    </el-container>
  </el-container>
</template>
