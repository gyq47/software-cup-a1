<script setup>
import { computed } from 'vue'
import { useRoute } from 'vue-router'

import MainLayout from './layouts/MainLayout.vue'

const route = useRoute()
const isLoginPage = computed(() => route.path === '/login')
</script>

<template>
  <router-view v-if="isLoginPage" />
  <MainLayout v-else />
</template>
