import axios from 'axios'
import { API_BASE_URL } from './config'

const http = axios.create({
  baseURL: API_BASE_URL,
  timeout: 30000,
})

export const getGraphOverview = async () => {
  const response = await http.get('/api/graph/overview')
  return response.data
}

export const searchGraphNodes = async (keyword = '', deviceModel = '') => {
  const response = await http.get('/api/graph/search', {
    params: {
      keyword,
      device_model: deviceModel || undefined,
    },
  })
  return response.data
}

export const expandGraphNode = async (nodeId, depth = 2, deviceModel = '') => {
  const response = await http.get('/api/graph/expand', {
    params: {
      node_id: nodeId,
      depth,
      device_model: deviceModel || undefined,
    },
  })
  return response.data
}

export const findGraphPath = async (source, target, maxDepth = 3, deviceModel = '') => {
  const response = await http.get('/api/graph/path', {
    params: {
      source,
      target,
      max_depth: maxDepth,
      device_model: deviceModel || undefined,
    },
  })
  return response.data
}

export const getGraphSubgraph = async (keyword = '', depth = 2, deviceModel = '') => {
  const response = await http.get('/api/graph/subgraph', {
    params: {
      keyword: keyword || undefined,
      depth,
      device_model: deviceModel || undefined,
    },
  })
  return response.data
}

export const extractGraphTriples = async ({ text, deviceModel = '', source = '', sourceType = '' }) => {
  const response = await http.post('/api/graph/extract-triples', {
    text,
    device_model: deviceModel || undefined,
    source: source || undefined,
    source_type: sourceType || undefined,
  })
  return response.data
}

export const commitGraphTriples = async ({ entities = [], triples = [], deviceModel = '', source = '', sourceType = '' }) => {
  const response = await http.post('/api/graph/commit-triples', {
    entities,
    triples,
    device_model: deviceModel || undefined,
    source: source || undefined,
    source_type: sourceType || undefined,
  })
  return response.data
}
