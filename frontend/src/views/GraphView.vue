<script setup>
import { ElMessage } from 'element-plus'
import { computed, onMounted, ref } from 'vue'

import {
  commitGraphTriples,
  expandGraphNode,
  extractGraphTriples,
  getGraphOverview,
  getGraphSubgraph,
  searchGraphNodes,
} from '../api/graph'

const loading = ref(false)
const keyword = ref('轴无法回零')
const deviceModel = ref('')
const overview = ref(null)
const graphData = ref({ nodes: [], edges: [], stats: {} })
const searchResults = ref([])
const selectedNode = ref(null)
const extractionLoading = ref(false)
const commitLoading = ref(false)
const extractionText = ref('轴无法回零通常可能与回零开关异常、PLC 输入信号异常、伺服驱动未使能或编码器异常有关。检修时应先检查急停回路和安全联锁状态，再检查回零开关信号是否进入 PLC，必要时进行报警复位和参数确认。')
const extractionResult = ref(null)

const deviceOptions = [
  { label: '全部设备', value: '' },
  { label: 'SINUMERIK 808D', value: 'SINUMERIK 808D' },
  { label: 'SINUMERIK 828D', value: 'SINUMERIK 828D' },
]

const relationLabel = (relation) => {
  const labels = {
    belongs_to: '归属',
    causes: '导致',
    affects: '影响',
    solves: '解决',
    checks: '检查',
    related_to: '关联',
    requires: '需要',
    prevents: '预防',
  }
  return labels[relation] || relation || '关联'
}

const nodeTypeTag = (type) => {
  const types = {
    device: 'success',
    alarm: 'danger',
    fault: 'warning',
    cause: 'primary',
    solution: 'success',
    risk: 'danger',
    manual: 'info',
    workflow_step: 'primary',
  }
  return types[type] || 'info'
}

const visibleEdges = computed(() => graphData.value.edges || [])
const visibleNodes = computed(() => graphData.value.nodes || [])

const loadGraph = async () => {
  loading.value = true
  try {
    overview.value = await getGraphOverview()
    graphData.value = await getGraphSubgraph(keyword.value, 2, deviceModel.value)
    const result = await searchGraphNodes(keyword.value, deviceModel.value)
    searchResults.value = result.nodes || []
    selectedNode.value = null
  } catch (error) {
    ElMessage.error('知识图谱加载失败，请检查后端服务')
  } finally {
    loading.value = false
  }
}

const selectNode = async (node) => {
  selectedNode.value = node
  loading.value = true
  try {
    graphData.value = await expandGraphNode(node.id, 2, deviceModel.value)
  } catch (error) {
    ElMessage.error('节点邻居扩展失败')
  } finally {
    loading.value = false
  }
}

const runTripleExtraction = async () => {
  if (!extractionText.value.trim()) {
    ElMessage.warning('请输入要抽取的文本')
    return
  }
  extractionLoading.value = true
  try {
    extractionResult.value = await extractGraphTriples({
      text: extractionText.value,
      deviceModel: deviceModel.value || 'common',
      source: 'graph_view_input',
      sourceType: 'manual_text',
    })
    if (extractionResult.value.success) {
      ElMessage.success('候选三元组抽取完成，请确认后入图谱')
    } else {
      ElMessage.warning((extractionResult.value.warnings || []).join('；') || '抽取失败')
    }
  } catch (error) {
    ElMessage.error('三元组抽取失败，请检查后端或模型配置')
  } finally {
    extractionLoading.value = false
  }
}

const commitTriples = async () => {
  if (!extractionResult.value?.entities?.length && !extractionResult.value?.triples?.length) {
    ElMessage.warning('暂无可入库候选')
    return
  }
  commitLoading.value = true
  try {
    const result = await commitGraphTriples({
      entities: extractionResult.value.entities || [],
      triples: extractionResult.value.triples || [],
      deviceModel: deviceModel.value || 'common',
      source: 'graph_view_input',
      sourceType: 'manual_text',
    })
    ElMessage.success(`入图谱完成：新增节点 ${result.added_nodes}，新增关系 ${result.added_edges}`)
    await loadGraph()
  } catch (error) {
    ElMessage.error('候选三元组入图谱失败')
  } finally {
    commitLoading.value = false
  }
}

onMounted(loadGraph)
</script>

<template>
  <section class="page graph-page">
    <div class="graph-hero">
      <div>
        <p class="eyebrow">Knowledge Graph</p>
        <h1>知识图谱</h1>
        <p>轻量工业检修知识图谱，用于展示设备、报警、故障、原因、检查步骤和手册依据之间的关系。</p>
      </div>
      <el-tag type="success" effect="dark">真实后端图谱</el-tag>
    </div>

    <el-card shadow="never" class="query-card">
      <div class="query-row">
        <el-select v-model="deviceModel" placeholder="设备型号" clearable>
          <el-option v-for="item in deviceOptions" :key="item.value" :label="item.label" :value="item.value" />
        </el-select>
        <el-input v-model="keyword" placeholder="输入故障、报警、部件或手册关键词" clearable @keyup.enter="loadGraph" />
        <el-button type="primary" color="#1d4ed8" :loading="loading" @click="loadGraph">查询图谱</el-button>
      </div>
    </el-card>

    <div class="overview-grid" v-if="overview">
      <el-card shadow="never" class="metric-card">
        <span>节点数</span>
        <strong>{{ overview.node_count }}</strong>
      </el-card>
      <el-card shadow="never" class="metric-card">
        <span>关系数</span>
        <strong>{{ overview.edge_count }}</strong>
      </el-card>
      <el-card shadow="never" class="metric-card">
        <span>设备类型</span>
        <strong>{{ Object.keys(overview.device_model_stats || {}).length }}</strong>
      </el-card>
      <el-card shadow="never" class="metric-card">
        <span>图谱版本</span>
        <strong>{{ overview.version }}</strong>
      </el-card>
    </div>

    <div class="graph-layout" v-loading="loading">
      <el-card shadow="never" class="node-panel">
        <template #header>
          <div class="panel-head">
            <span>节点搜索结果</span>
            <el-tag>{{ searchResults.length }} 个</el-tag>
          </div>
        </template>
        <el-empty v-if="!searchResults.length" description="未找到节点" />
        <div v-else class="node-list">
          <button v-for="node in searchResults" :key="node.id" class="node-card" type="button" @click="selectNode(node)">
            <div>
              <strong>{{ node.name }}</strong>
              <p>{{ node.description }}</p>
            </div>
            <div class="node-tags">
              <el-tag size="small" :type="nodeTypeTag(node.type)">{{ node.type }}</el-tag>
              <el-tag size="small" effect="plain">{{ node.device_model || 'common' }}</el-tag>
            </div>
          </button>
        </div>
      </el-card>

      <el-card shadow="never" class="graph-panel">
        <template #header>
          <div class="panel-head">
            <span>关系子图</span>
            <el-tag type="primary">{{ visibleNodes.length }} 节点 / {{ visibleEdges.length }} 关系</el-tag>
          </div>
        </template>
        <el-empty v-if="!visibleNodes.length" description="图谱为空或无匹配关系" />
        <div v-else class="graph-chain">
          <div class="graph-node-cloud">
            <button
              v-for="node in visibleNodes"
              :key="node.id"
              class="graph-node"
              type="button"
              :class="{ active: selectedNode?.id === node.id }"
              @click="selectNode(node)"
            >
              <span>{{ node.name }}</span>
              <small>{{ node.type }} · {{ node.device_model || 'common' }}</small>
            </button>
          </div>
          <div class="edge-list">
            <div v-for="edge in visibleEdges" :key="edge.id" class="edge-card">
              <el-tag type="primary" effect="plain">{{ relationLabel(edge.relation) }}</el-tag>
              <span>{{ edge.source }} → {{ edge.target }}</span>
              <p>{{ edge.evidence }}</p>
              <small>来源：{{ edge.source_label || edge.source || 'graph' }} · {{ edge.device_model || 'common' }}</small>
            </div>
          </div>
        </div>
      </el-card>
    </div>

    <el-card shadow="never" class="extraction-card">
      <template #header>
        <div class="panel-head">
          <span>文本抽取候选三元组</span>
          <el-tag type="warning" effect="plain">人工确认后入图谱</el-tag>
        </div>
      </template>
      <div class="extract-grid">
        <div class="extract-input">
          <el-input
            v-model="extractionText"
            type="textarea"
            :rows="7"
            resize="none"
            placeholder="粘贴维修手册片段、审核案例或现场经验文本"
          />
          <div class="extract-actions">
            <el-button type="primary" color="#1d4ed8" :loading="extractionLoading" @click="runTripleExtraction">
              抽取候选关系
            </el-button>
            <el-button color="#111827" :loading="commitLoading" :disabled="!extractionResult?.success" @click="commitTriples">
              确认入图谱
            </el-button>
          </div>
          <el-alert
            v-if="extractionResult?.warnings?.length"
            :title="extractionResult.warnings.join('；')"
            type="warning"
            :closable="false"
            show-icon
          />
        </div>
        <div class="candidate-panel">
          <el-empty v-if="!extractionResult" description="抽取后在此查看候选实体和关系" />
          <template v-else>
            <h3>候选实体</h3>
            <div class="candidate-list">
              <div v-for="entity in extractionResult.entities" :key="`${entity.name}-${entity.type}`" class="candidate-item">
                <strong>{{ entity.name }}</strong>
                <el-tag size="small" :type="nodeTypeTag(entity.type)">{{ entity.type }}</el-tag>
                <span>{{ entity.description || '无描述' }}</span>
              </div>
            </div>
            <h3>候选关系</h3>
            <div class="candidate-list">
              <div v-for="triple in extractionResult.triples" :key="`${triple.subject}-${triple.relation}-${triple.object}`" class="candidate-item">
                <strong>{{ triple.subject }} → {{ triple.object }}</strong>
                <el-tag size="small" type="primary">{{ relationLabel(triple.relation) }}</el-tag>
                <span>{{ triple.evidence || '无证据说明' }}</span>
                <small>confidence {{ Number(triple.confidence || 0).toFixed(2) }}</small>
              </div>
            </div>
          </template>
        </div>
      </div>
    </el-card>
  </section>
</template>

<style scoped>
.graph-page { gap: 18px; }
.graph-hero { display: flex; align-items: flex-end; justify-content: space-between; gap: 16px; padding: 22px 24px; border: 1px solid #1f2a3a; border-radius: 10px; background: #111827; color: #fff; }
.graph-hero h1 { margin: 4px 0 8px; }
.graph-hero p { margin: 0; color: #b6c2d2; }
.query-card, .node-panel, .graph-panel, .metric-card { border: 1px solid #dbe2ea; border-radius: 10px; }
.query-row { display: grid; grid-template-columns: 220px 1fr auto; gap: 12px; }
.overview-grid { display: grid; grid-template-columns: repeat(4, minmax(0, 1fr)); gap: 12px; }
.metric-card span { display: block; color: #64748b; font-size: 13px; }
.metric-card strong { display: block; margin-top: 8px; color: #0f172a; font-size: 26px; }
.graph-layout { display: grid; grid-template-columns: 360px minmax(0, 1fr); gap: 16px; }
.panel-head { display: flex; align-items: center; justify-content: space-between; gap: 10px; font-weight: 800; }
.node-list { display: grid; gap: 10px; }
.node-card { display: grid; gap: 8px; width: 100%; padding: 12px; border: 1px solid #dbeafe; border-radius: 8px; background: #f8fafc; text-align: left; cursor: pointer; }
.node-card strong { color: #0f172a; }
.node-card p { margin: 6px 0 0; color: #64748b; line-height: 1.6; }
.node-tags { display: flex; flex-wrap: wrap; gap: 6px; }
.graph-chain { display: grid; gap: 16px; }
.graph-node-cloud { display: flex; flex-wrap: wrap; gap: 10px; padding: 12px; border-radius: 8px; background: #f1f5f9; }
.graph-node { display: grid; gap: 4px; padding: 10px 12px; border: 1px solid #bfdbfe; border-radius: 8px; background: #fff; color: #1e3a8a; cursor: pointer; }
.graph-node.active { border-color: #1d4ed8; background: #eff6ff; }
.graph-node span { font-weight: 900; }
.graph-node small { color: #64748b; }
.edge-list { display: grid; gap: 10px; }
.edge-card { display: grid; gap: 6px; padding: 12px; border-left: 4px solid #1d4ed8; border-radius: 8px; background: #f8fafc; }
.edge-card span { font-family: Consolas, monospace; color: #334155; }
.edge-card p { margin: 0; color: #475569; }
.edge-card small { color: #64748b; }
.extraction-card { border: 1px solid #dbe2ea; border-radius: 10px; }
.extract-grid { display: grid; grid-template-columns: minmax(0, 1fr) minmax(360px, 0.9fr); gap: 16px; }
.extract-input { display: grid; gap: 12px; }
.extract-actions { display: flex; flex-wrap: wrap; gap: 10px; }
.candidate-panel { min-height: 260px; padding: 12px; border: 1px solid #dbeafe; border-radius: 8px; background: #f8fafc; }
.candidate-panel h3 { margin: 0 0 10px; color: #0f172a; }
.candidate-list { display: grid; gap: 8px; margin-bottom: 14px; }
.candidate-item { display: grid; gap: 6px; padding: 10px; border-radius: 8px; background: #fff; color: #334155; }
.candidate-item strong { color: #0f172a; }
.candidate-item small { color: #64748b; font-family: Consolas, monospace; }
@media (max-width: 1180px) { .graph-layout, .query-row, .overview-grid { grid-template-columns: 1fr; } }
@media (max-width: 1180px) { .extract-grid { grid-template-columns: 1fr; } }
</style>
