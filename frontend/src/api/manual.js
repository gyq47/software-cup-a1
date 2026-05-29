import axios from 'axios'

const http = axios.create({
  baseURL: 'http://localhost:8000',
  timeout: 120000,
})

export const uploadManual = async (file, options = {}, onUploadProgress) => {
  if (typeof options === 'function') {
    onUploadProgress = options
    options = {}
  }
  const formData = new FormData()
  formData.append('file', file)
  if (options.deviceModel) formData.append('device_model', options.deviceModel)
  if (options.manualType) formData.append('manual_type', options.manualType)

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

export const hybridSearch = async (q, topK = 5, deviceModel = '') => {
  const response = await http.get('/api/manual/hybrid-search', {
    params: {
      q,
      top_k: topK,
      device_model: deviceModel || undefined,
    },
  })

  return response.data
}

export const getManualList = async (params = {}) => {
  const response = await http.get('/api/manual/list', { params })
  return response.data
}

export const reindexManual = async (payload) => {
  const response = await http.post('/api/manual/reindex', payload)
  return response.data
}

export const rebuildManualIndex = async () => {
  const response = await http.post('/api/manual/rebuild-index')
  return response.data
}
