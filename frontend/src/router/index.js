import { createRouter, createWebHistory } from 'vue-router'

import { useAuthStore } from '../stores/auth'
import AdminView from '../views/AdminView.vue'
import ChatView from '../views/ChatView.vue'
import DiagnosisView from '../views/DiagnosisView.vue'
import FeedbackView from '../views/FeedbackView.vue'
import GraphView from '../views/GraphView.vue'
import HomeView from '../views/HomeView.vue'
import LoginView from '../views/LoginView.vue'
import SearchView from '../views/SearchView.vue'
import UploadView from '../views/UploadView.vue'
import WorkflowView from '../views/WorkflowView.vue'

const routes = [
  {
    path: '/login',
    name: 'login',
    component: LoginView,
    meta: {
      public: true,
    },
  },
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
    meta: {
      roles: ['admin'],
    },
  },
  {
    path: '/search',
    name: 'search',
    component: SearchView,
    meta: {
      roles: ['expert', 'admin'],
    },
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
  {
    path: '/graph',
    name: 'graph',
    component: GraphView,
    meta: {
      roles: ['expert', 'admin'],
    },
  },
  {
    path: '/admin',
    name: 'admin',
    component: AdminView,
    meta: {
      roles: ['admin'],
    },
  },
  {
    path: '/rules',
    name: 'rules',
    component: AdminView,
    meta: {
      roles: ['admin'],
    },
  },
]

const router = createRouter({
  history: createWebHistory(),
  routes,
})

router.beforeEach((to) => {
  const auth = useAuthStore()
  auth.restore()

  if (to.meta.public) {
    return auth.isLogin ? '/' : true
  }

  if (!auth.isLogin) {
    return {
      path: '/login',
      query: {
        redirect: to.fullPath,
      },
    }
  }

  const roles = to.meta.roles || []
  if (roles.length && !auth.hasRole(roles)) {
    return '/'
  }

  return true
})

export default router
