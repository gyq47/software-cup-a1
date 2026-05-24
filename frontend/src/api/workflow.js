import axios from 'axios'

const http = axios.create({
  baseURL: 'http://localhost:8000',
  timeout: 120000,
})

export const generateWorkflow = async (task, top_k = 5) => {
  const response = await http.post('/api/workflow/generate', {
    task,
    top_k,
  })

  return response.data
}
