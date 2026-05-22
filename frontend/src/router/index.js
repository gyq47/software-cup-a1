import { createRouter, createWebHistory } from 'vue-router'

import ChatView from '../views/ChatView.vue'
import HomeView from '../views/HomeView.vue'
import SearchView from '../views/SearchView.vue'
import UploadView from '../views/UploadView.vue'

const routes = [
  {
    path: '/',
    name: 'home',
    component: HomeView,
  },
  {
    path: '/chat',
    name: 'chat',
    component: ChatView,
  },
  {
    path: '/upload',
    name: 'upload',
    component: UploadView,
  },
  {
    path: '/search',
    name: 'search',
    component: SearchView,
  },
]

const router = createRouter({
  history: createWebHistory(),
  routes,
})

export default router
