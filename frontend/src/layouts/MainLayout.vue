<script setup>
import {
  ChatDotRound,
  Camera,
  DocumentAdd,
  EditPen,
  House,
  Operation,
  Setting,
  Search,
  Share,
} from '@element-plus/icons-vue'
import { computed } from 'vue'
import { useRoute, useRouter } from 'vue-router'

import { useAuthStore } from '../stores/auth'

const route = useRoute()
const router = useRouter()
const auth = useAuthStore()

const activeMenu = computed(() => route.path)
const menuItems = computed(() => {
  const items = [
    { index: '/', label: '首页', icon: House, roles: ['worker', 'expert', 'admin'] },
    { index: '/chat', label: '智能问答', icon: ChatDotRound, roles: ['worker', 'expert', 'admin'] },
    { index: '/diagnosis', label: '多模态诊断', icon: Camera, roles: ['worker', 'expert', 'admin'] },
    { index: '/workflow', label: '标准作业卡', icon: Operation, roles: ['worker', 'expert', 'admin'] },
    { index: '/feedback', label: auth.atLeast('expert') ? '专家审核中心' : '知识审核闭环', icon: EditPen, roles: ['worker', 'expert', 'admin'] },
    { index: '/upload', label: 'PDF上传', icon: DocumentAdd, roles: ['admin'] },
    { index: '/search', label: '知识检索', icon: Search, roles: ['expert', 'admin'] },
    { index: '/graph', label: '知识图谱', icon: Share, roles: ['expert', 'admin'] },
    { index: '/rules', label: '规则管理', icon: Setting, roles: ['admin'] },
    { index: '/admin', label: '系统管理', icon: Setting, roles: ['admin'] },
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
          <div class="system-status">Backend API · Document Search · Repair Assistant</div>
        </div>
        <div class="user-area">
          <el-avatar :size="34">{{ auth.display_name?.slice(0, 1) }}</el-avatar>
          <div class="user-meta">
            <strong>{{ auth.display_name }}</strong>
            <el-tag size="small" type="info">{{ auth.role }}</el-tag>
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
