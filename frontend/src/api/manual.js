import axios from 'axios'

const http = axios.create({
  baseURL: 'http://localhost:8000',
  timeout: 120000,
})

export const uploadManual = async (file, onUploadProgress) => {
  const formData = new FormData()
  formData.append('file', file)

  const response = await http.post('/api/manual/upload', formData, {
    headers: {
      'Content-Type': 'multipart/form-data',
    },
    onUploadProgress,
  })

  return response.data
}

export const semanticSearch = async (q, topK = 5) => {
  const response = await http.get('/api/manual/semantic-search', {
    params: {
      q,
      top_k: topK,
    },
  })

  return response.data
}
