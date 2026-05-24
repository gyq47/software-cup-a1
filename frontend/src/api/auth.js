import axios from 'axios'

const http = axios.create({
  baseURL: 'http://localhost:8000',
  timeout: 30000,
})

export const loginApi = async (username, password, role) => {
  const response = await http.post('/api/auth/login', {
    username,
    password,
    role,
  })
  return response.data
}

export const logoutApi = async () => {
  const response = await http.post('/api/auth/logout')
  return response.data
}
