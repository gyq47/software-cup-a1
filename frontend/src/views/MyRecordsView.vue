<script setup>
const records = [
  {
    time: '2026-05-27 09:20',
    device_model: 'SINUMERIK 828D',
    alarm_code: '300500',
    fault: 'X轴无法回零',
    level: '一级检修',
    mode: '基础模式',
    workflow: '是',
    correction: '否',
    status: '已完成',
  },
  {
    time: '2026-05-26 15:40',
    device_model: 'SINUMERIK 808D',
    alarm_code: 'PLC-I/O',
    fault: '自动加工无法启动',
    level: '二级检修',
    mode: '增强模式',
    workflow: '是',
    correction: '是',
    status: '待审核',
  },
]
</script>

<template>
  <section class="page records-page">
    <div class="records-hero">
      <div>
        <p class="eyebrow">Maintenance Records</p>
        <h1>我的检修记录</h1>
        <p>查看历史分析、作业卡生成和修正提交状态。</p>
      </div>
    </div>

    <el-card shadow="never" class="records-card">
      <el-table :data="records" stripe>
        <el-table-column prop="time" label="时间" width="160" />
        <el-table-column prop="device_model" label="设备型号" width="150" />
        <el-table-column prop="alarm_code" label="报警代码" width="130" />
        <el-table-column prop="fault" label="故障描述" min-width="180" />
        <el-table-column prop="level" label="检修等级" width="120" />
        <el-table-column prop="mode" label="模式" width="100" />
        <el-table-column prop="workflow" label="作业卡" width="100" />
        <el-table-column prop="correction" label="提交修正" width="110" />
        <el-table-column prop="status" label="状态" width="110">
          <template #default="{ row }">
            <el-tag :type="row.status === '已完成' ? 'success' : 'warning'">{{ row.status }}</el-tag>
          </template>
        </el-table-column>
      </el-table>
    </el-card>
  </section>
</template>

<style scoped>
.records-hero { padding: 22px 24px; border-radius: 10px; background: #111827; color: #fff; }
.records-hero h1 { margin: 6px 0 8px; font-size: 30px; }
.records-hero p:last-child { margin: 0; color: #aeb8c8; }
.records-card { border: 1px solid #dbe2ea; border-radius: 10px; }
</style>
