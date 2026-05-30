import axios from 'axios'
import { API_BASE_URL } from './config'

const http = axios.create({
  baseURL: API_BASE_URL,
  timeout: 120000,
})

export const submitFeedback = async (payload) => {
  const response = await http.post('/api/feedback/submit', payload)
  return response.data
}

export const getPendingFeedback = async () => {
  const response = await http.get('/api/feedback/pending')
  return response.data
}

export const reviewFeedback = async (payload) => {
  const response = await http.post('/api/feedback/review', payload)
  return response.data
}

export const getFeedbackCases = async () => {
  const response = await http.get('/api/feedback/cases')
  return response.data
}
