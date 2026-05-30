import axios from 'axios'
import { API_BASE_URL } from './config'

const http = axios.create({
  baseURL: API_BASE_URL,
  timeout: 120000,
})

export const sendChat = async (question, top_k = 5, deviceModel = '') => {
  const response = await http.post('/api/chat', {
    question,
    top_k,
    device_model: deviceModel || undefined,
  })

  return response.data
}
