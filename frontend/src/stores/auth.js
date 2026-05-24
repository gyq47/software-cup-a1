import { defineStore } from 'pinia'

import { loginApi, logoutApi } from '../api/auth'

const STORAGE_KEY = 'software-cup-a1-auth'
const ROLE_LEVELS = {
  worker: 1,
  expert: 2,
  admin: 3,
}

export const useAuthStore = defineStore('auth', {
  state: () => ({
    token: '',
    username: '',
    role: '',
    display_name: '',
  }),
  getters: {
    isLogin: (state) => Boolean(state.token),
    roleLevel: (state) => ROLE_LEVELS[state.role] || 0,
  },
  actions: {
    async login(username, password) {
      const data = await loginApi(username, password)
      if (!data.success) {
        throw new Error(data.message || '登录失败')
      }
      this.token = data.token
      this.username = data.username
      this.role = data.role
      this.display_name = data.display_name
      this.persist()
      return data
    },
    async logout() {
      try {
        await logoutApi()
      } finally {
        this.token = ''
        this.username = ''
        this.role = ''
        this.display_name = ''
        window.localStorage.removeItem(STORAGE_KEY)
      }
    },
    restore() {
      const raw = window.localStorage.getItem(STORAGE_KEY)
      if (!raw) return
      try {
        const data = JSON.parse(raw)
        this.token = data.token || ''
        this.username = data.username || ''
        this.role = data.role || ''
        this.display_name = data.display_name || ''
      } catch (error) {
        window.localStorage.removeItem(STORAGE_KEY)
      }
    },
    persist() {
      window.localStorage.setItem(
        STORAGE_KEY,
        JSON.stringify({
          token: this.token,
          username: this.username,
          role: this.role,
          display_name: this.display_name,
        }),
      )
    },
    hasRole(requiredRoles = []) {
      if (!requiredRoles.length) return true
      return requiredRoles.includes(this.role)
    },
    atLeast(role) {
      return this.roleLevel >= (ROLE_LEVELS[role] || 0)
    },
  },
})
