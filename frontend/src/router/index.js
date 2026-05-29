import { createRouter, createWebHistory } from 'vue-router'

import { useAuthStore } from '../stores/auth'
import ChatView from '../views/ChatView.vue'
import DiagnosisView from '../views/DiagnosisView.vue'
import FeedbackView from '../views/FeedbackView.vue'
import GraphView from '../views/GraphView.vue'
import HomeView from '../views/HomeView.vue'
import KnowledgeReviewView from '../views/KnowledgeReviewView.vue'
import LoginView from '../views/LoginView.vue'
import ManualsView from '../views/ManualsView.vue'
import MyRecordsView from '../views/MyRecordsView.vue'
import SearchView from '../views/SearchView.vue'
import SystemConfigView from '../views/SystemConfigView.vue'
import SystemDiagnosticsView from '../views/SystemDiagnosticsView.vue'
import UploadView from '../views/UploadView.vue'
import UsersView from '../views/UsersView.vue'
import WorkbenchView from '../views/WorkbenchView.vue'
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
    redirect: '/workbench',
  },
  {
    path: '/workbench',
    name: 'workbench',
    component: WorkbenchView,
    meta: {
      roles: ['worker', 'expert', 'admin'],
    },
  },
  {
    path: '/my-records',
    name: 'my-records',
    component: MyRecordsView,
    meta: {
      roles: ['worker'],
    },
  },
  {
    path: '/review',
    name: 'review',
    component: KnowledgeReviewView,
    meta: {
      roles: ['expert'],
    },
  },
  {
    path: '/manuals',
    name: 'manuals',
    component: ManualsView,
    meta: {
      roles: ['expert', 'admin'],
    },
  },
  {
    path: '/users',
    name: 'users',
    component: UsersView,
    meta: {
      roles: ['admin'],
    },
  },
  {
    path: '/system',
    name: 'system',
    component: SystemConfigView,
    meta: {
      roles: ['admin'],
    },
  },
  {
    path: '/diagnostics',
    name: 'diagnostics',
    component: SystemDiagnosticsView,
    meta: {
      roles: ['admin'],
    },
  },
  {
    path: '/home',
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
      roles: ['expert', 'admin'],
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
    meta: {
      roles: ['worker'],
    },
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
    component: SystemConfigView,
    meta: {
      roles: ['admin'],
    },
  },
  {
    path: '/rules',
    name: 'rules',
    component: SystemConfigView,
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
    return auth.isLogin ? '/workbench' : true
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
    return '/workbench'
  }

  return true
})

export default router
