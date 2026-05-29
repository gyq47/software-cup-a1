import { sendChat } from './chat'
import { diagnoseImage } from './diagnosis'
import { submitFeedback } from './feedback'
import { generateWorkflow as requestWorkflow } from './workflow'

export const analyzeFault = async ({ image, text, deviceModel, alarmCode, level, mode }) => {
  if (image) {
    return diagnoseImage({
      image,
      text: [text, alarmCode].filter(Boolean).join(' '),
      deviceModel,
      mode,
      level,
      alarmCode,
    })
  }

  const question = [
    deviceModel && `设备型号：${deviceModel}`,
    alarmCode && `报警代码：${alarmCode}`,
    text && `故障描述：${text}`,
    level && `检修等级：${level}`,
    mode && `当前模式：${mode}`,
  ].filter(Boolean).join('\n')

  return sendChat(question, 5, deviceModel)
}

export const generateWorkbenchWorkflow = async (task, topK = 5, deviceModel = '') => {
  return requestWorkflow(task, topK, deviceModel)
}

export const submitCorrection = async (payload) => {
  return submitFeedback({
    source_type: 'workflow',
    source_id: '',
    original_question: payload.original_question,
    original_answer: payload.original_answer,
    correction_type: payload.correction_type || 'other',
    correction_text: payload.correction_text,
    related_device: payload.related_device || '',
    related_fault: payload.related_fault || '',
    submitter_role: 'worker',
    priority: payload.priority || 'medium',
  })
}

export const getHistoryReferences = async () => {
  // 后续替换为真实历史检修记录/已沉淀知识接口。
  return Promise.resolve([
    {
      device_model: 'SINUMERIK 828D',
      alarm_code: 'REF-AXIS',
      fault: 'X轴无法回零',
      reason: '回零开关信号未进入 PLC 输入点',
      solution: '检查开关、接线端子和 PLC 输入状态后重新回零',
      source: '已沉淀知识',
      status: 'approved',
    },
  ])
}
