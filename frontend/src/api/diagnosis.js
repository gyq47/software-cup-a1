import axios from 'axios'

const http = axios.create({
  baseURL: 'http://localhost:8000',
  timeout: 180000,
})

export const diagnoseImage = async ({ image, text, deviceModel }) => {
  const formData = new FormData()
  formData.append('image', image)
  if (text) formData.append('text', text)
  if (deviceModel) formData.append('device_model', deviceModel)

  const response = await http.post('/api/diagnosis/image', formData, {
    headers: {
      'Content-Type': 'multipart/form-data',
    },
  })

  return response.data
}
