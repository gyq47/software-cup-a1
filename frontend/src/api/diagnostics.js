import { generateWorkflow } from './workflow'
import { getManualList, semanticSearch } from './manual'
import { getGraphSubgraph } from './graph'
import axios from 'axios'
import { API_BASE_URL } from './config'

const api = axios.create({
  baseURL: API_BASE_URL,
})

export const getSystemHealth = async () => {
  const { data } = await api.get('/api/system/health')
  return data
}

export const getSystemDiagnostics = async (deepCheck = false) => {
  const { data } = await api.get('/api/system/diagnostics', {
    params: { deep_check: deepCheck },
  })
  return data
}

export const getSystemStatus = async () => {
  return getSystemHealth()
}

export const diagnoseOcr = async () => {
  // 后续替换为真实 OCR 诊断接口。
  return Promise.resolve({
    raw_text: 'SINUMERIK 828D Alarm 300500 X axis reference point not reached',
    alarm_codes: ['300500'],
    parameter_ids: ['X-Axis'],
    device_models: ['SINUMERIK 828D'],
    confidence: '',
  })
}

export const diagnoseRetrieval = async (query) => {
  try {
    const data = await semanticSearch(query, 5)
    return (data.results || []).map((item) => ({
      ...item,
      retrieval_type: 'LangChain / Hybrid',
      score: item.final_score ?? item.score ?? item.semantic_score ?? 0,
    }))
  } catch (error) {
    return [
      {
        chunk_id: 'diagnostic-sample-001',
        filename: 'SINUMERIK 828D 诊断手册.pdf',
        page: 12,
        score: 0.86,
        retrieval_type: 'LangChain / Hybrid',
        content: '轴无法回零时，应检查回零开关、PLC 输入信号、驱动使能状态和安全回路状态。',
      },
    ]
  }
}

export const diagnoseGraph = async (keyword) => {
  const data = await getGraphSubgraph(keyword, 2)
  const nodeNames = (data.nodes || []).map((node) => node.name)
  return {
    keyword,
    nodes: nodeNames,
    edges: data.edges || [],
    path: nodeNames.join(' -> '),
    expanded_query: nodeNames.join(' '),
    stats: data.stats || {},
  }
}

export const diagnoseWorkflow = async ({ fault, deviceModel, level }) => {
  try {
    return await generateWorkflow(`${deviceModel || ''} ${fault || '设备故障'} ${level || ''}`.trim(), 5)
  } catch (error) {
    const stepCount = level?.startsWith('三级') ? 7 : level?.startsWith('二级') ? 5 : 3
    return {
      workflow: {
        title: `${fault || '设备故障'}标准作业卡`,
        tools: ['万用表', '绝缘工具', '记录表'],
        safety_notices: ['停机断电', '急停确认', '防夹伤'],
        steps: Array.from({ length: stepCount }, (_, index) => ({
          step_no: index + 1,
          title: `步骤${index + 1}`,
          description: '按检修等级执行对应检查项。',
          reference: '维修手册 第1页',
        })),
        final_check: ['报警复位', '低速试运行', '记录检修结果'],
      },
    }
  }
}

export const diagnoseCompliance = async () => {
  return Promise.resolve({
    passed: false,
    passed_items: ['急停检查', '驱动复位', '完工测试'],
    missing_items: ['断电确认', '参数备份', '安全联锁检查'],
    risks: ['缺少断电确认会增加误启动风险。'],
    suggestions: ['在步骤1前补充停机、断电、挂牌和联锁确认。'],
  })
}

export const getManualIndexStatus = async () => {
  const data = await getManualList()
  return {
    items: data.items || [],
    total: data.total || 0,
    indexed_count: data.indexed_count || 0,
    total_chunks: data.total_chunks || 0,
    vector_store_dir: data.vector_store_dir || '',
    vector_store_ready: Boolean(data.vector_store_ready),
  }
}

export const getModelStatus = async () => {
  // 后续替换为真实模型状态接口，API Key 不在前端明文展示。
  return Promise.resolve({
    llm: 'configured',
    vision: 'available',
    ocr: 'available',
    rag_backend: 'LangChain + Chroma',
    vector_store: 'backend/data/vector_store/chroma',
    api_key: 'sk-****abcd',
    running_mode: '基础模式 / 增强模式手动开启',
  })
}
