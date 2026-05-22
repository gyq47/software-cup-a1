import axios from 'axios'

const http = axios.create({
  baseURL: 'http://localhost:8000',
  timeout: 120000,
})

export const sendChat = async (question, top_k = 5) => {
  const response = await http.post('/api/chat', {
    question,
    top_k,
  })

  return response.data
}
