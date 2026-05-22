<script setup>
import {
  ChatDotRound,
  DocumentAdd,
  House,
  Search,
} from '@element-plus/icons-vue'
import { computed } from 'vue'
import { useRoute, useRouter } from 'vue-router'

const route = useRoute()
const router = useRouter()

const activeMenu = computed(() => route.path)

const handleSelect = (path) => {
  router.push(path)
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
        <el-menu-item index="/">
          <el-icon><House /></el-icon>
          <span>首页</span>
        </el-menu-item>
        <el-menu-item index="/chat">
          <el-icon><ChatDotRound /></el-icon>
          <span>AI检修助手</span>
        </el-menu-item>
        <el-menu-item index="/upload">
          <el-icon><DocumentAdd /></el-icon>
          <span>PDF上传</span>
        </el-menu-item>
        <el-menu-item index="/search">
          <el-icon><Search /></el-icon>
          <span>知识检索</span>
        </el-menu-item>
      </el-menu>
    </el-aside>

    <el-container class="main-area">
      <el-header class="topbar">
        <div>
          <div class="system-name">基于多模态大模型技术的设备检修知识检索与作业系统</div>
          <div class="system-status">Backend API · Document Search · Repair Assistant</div>
        </div>
        <el-tag type="success" effect="dark">运行中</el-tag>
      </el-header>

      <el-main class="content">
        <router-view />
      </el-main>
    </el-container>
  </el-container>
</template>
