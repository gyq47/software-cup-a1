import { createRouter, createWebHistory } from 'vue-router'

import ChatView from '../views/ChatView.vue'
import DiagnosisView from '../views/DiagnosisView.vue'
import FeedbackView from '../views/FeedbackView.vue'
import HomeView from '../views/HomeView.vue'
import SearchView from '../views/SearchView.vue'
import UploadView from '../views/UploadView.vue'
import WorkflowView from '../views/WorkflowView.vue'

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
  {
    path: '/workflow',
    name: 'workflow',
    component: WorkflowView,
  },
  {
    path: '/diagnosis',
    name: 'diagnosis',
    component: DiagnosisView,
  },
  {
    path: '/feedback',
    name: 'feedback',
    component: FeedbackView,
  },
]

const router = createRouter({
  history: createWebHistory(),
  routes,
})

export default router
