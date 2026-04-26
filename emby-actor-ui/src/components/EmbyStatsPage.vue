<!-- src/components/EmbyStatsPage.vue -->
<template>
  <div class="modular-page-container">
    
    <!-- 顶部控制栏 -->
    <div class="page-header-module" style="display: flex; justify-content: space-between; align-items: flex-end; flex-wrap: wrap; gap: 16px;">
      <div>
        <h1 class="greeting-title" style="display: flex; align-items: center; gap: 12px;">
          <n-icon color="#8a2be2"><StatsChart /></n-icon> Emby 仪表盘
        </h1>
        <p class="greeting-subtitle">全站播放数据统计，依赖 Playback Reporting 插件。</p>
      </div>
      <div class="filter-section" style="display: flex; gap: 12px; align-items: center;">
        <n-radio-group v-model:value="timeRange" size="small" @update:value="fetchData">
          <n-radio-button :value="7">7天</n-radio-button>
          <n-radio-button :value="30">30天</n-radio-button>
          <n-radio-button :value="90">90天</n-radio-button>
          <n-radio-button :value="365">全年</n-radio-button>
        </n-radio-group>
        <n-button circle size="small" type="primary" ghost @click="fetchData" :loading="loading">
          <template #icon><n-icon><Refresh /></n-icon></template>
        </n-button>
      </div>
    </div>

    <n-spin :show="loading">
      <!-- 1. 核心指标卡片 (响应式: 手机2列, 电脑4列) -->
      <n-grid cols="2 m:4" :x-gap="16" :y-gap="16" responsive="screen" style="margin-bottom: 24px;">
        <n-gi v-for="(item, index) in summaryCards" :key="index">
          <n-card :bordered="false" class="dashboard-card stat-module">
            <div style="display: flex; align-items: center; gap: 16px;">
              <div class="stat-icon-glass" :style="{ color: item.color }">
                <n-icon :component="item.icon" size="28" />
              </div>
              <div>
                <div style="font-size: 13px; color: rgba(255,255,255,0.6);">{{ item.label }}</div>
                <div style="font-size: 24px; font-weight: bold; color: #fff;">
                  {{ item.value }} <span style="font-size: 12px; font-weight: normal; color: rgba(255,255,255,0.4);">{{ item.unit }}</span>
                </div>
              </div>
            </div>
          </n-card>
        </n-gi>
      </n-grid>

      <!-- 2. 图表区域 (响应式: 手机1列, 电脑2列) -->
      <n-grid cols="1 m:2" :x-gap="24" :y-gap="24" responsive="screen" style="margin-bottom: 24px;">
        <!-- 左侧：播放趋势 -->
        <n-gi>
          <n-card :bordered="false" class="dashboard-card chart-module" style="height: 100%;">
            <template #header><span class="card-title">播放趋势</span></template>
            <div style="height: 300px; width: 100%;">
              <v-chart class="chart" :option="trendChartOption" autoresize />
            </div>
          </n-card>
        </n-gi>
        <!-- 右侧：用户排行 -->
        <n-gi>
          <n-card :bordered="false" class="dashboard-card chart-module" style="height: 100%;">
            <template #header><span class="card-title">用户观看时长 (Top 10)</span></template>
            <div style="height: 300px; width: 100%;">
              <v-chart class="chart" :option="userChartOption" autoresize />
            </div>
          </n-card>
        </n-gi>
      </n-grid>

      <!-- 3. 热门媒体 (海报墙) -->
      <n-card :bordered="false" class="dashboard-card">
        <template #header><span class="card-title">热门媒体 (Top 20)</span></template>
        <n-grid cols="3 s:4 m:6 l:8 xl:10" :x-gap="12" :y-gap="16" responsive="screen">
          <n-gi v-for="(item, index) in statsData.media_rank" :key="item.id">
           <div class="poster-wrapper" @click="openEmbyItem(item.id)">
              <div class="rank-badge" :class="'rank-' + (index + 1)">{{ index + 1 }}</div>
              <div class="play-count-badge">{{ item.count }}次</div>
              <n-image lazy preview-disabled :src="getPosterUrl(item)" fallback-src="https://via.placeholder.com/300x450?text=No+Image" object-fit="cover" class="poster-img" />
              <div class="poster-title">{{ item.name }}</div>
            </div>
          </n-gi>
        </n-grid>
      </n-card>
    </n-spin>
  </div>
</template>

<script setup>
// 脚本部分完全保持你原有的逻辑不变
import { ref, onMounted, computed } from 'vue';
import axios from 'axios';
import { useMessage } from 'naive-ui';
import { StatsChart, Refresh, Play, Time, People, Videocam } from '@vicons/ionicons5';
import VChart from 'vue-echarts';
import { use } from 'echarts/core';
import { CanvasRenderer } from 'echarts/renderers';
import { BarChart, LineChart } from 'echarts/charts';
import { GridComponent, TooltipComponent, LegendComponent, TitleComponent } from 'echarts/components';

use([CanvasRenderer, BarChart, LineChart, GridComponent, TooltipComponent, LegendComponent, TitleComponent]);

const message = useMessage();
const loading = ref(false);
const timeRange = ref(30);
const statsData = ref({ total_plays: 0, total_duration_hours: 0, active_users: 0, watched_items: 0, chart_trend: { dates: [], counts: [], hours: [] }, chart_users: { names: [], hours: [] }, emby_url: '', emby_server_id: '', media_rank: [] });

const summaryCards = computed(() => [
  { label: '播放次数', value: statsData.value.total_plays, unit: '次', icon: Play, color: '#63e2b7' },
  { label: '播放时长', value: statsData.value.total_duration_hours, unit: '小时', icon: Time, color: '#f2c97d' },
  { label: '活跃用户', value: statsData.value.active_users, unit: '人', icon: People, color: '#70c0e8' },
  { label: '观看内容', value: statsData.value.watched_items, unit: '部', icon: Videocam, color: '#e88080' },
]);

const trendChartOption = computed(() => ({
  tooltip: { trigger: 'axis', backgroundColor: 'rgba(20, 25, 35, 0.85)', borderColor: 'rgba(255,255,255,0.1)', textStyle: { color: '#fff' } },
  legend: { data: ['播放次数', '时长(小时)'], bottom: 0, textStyle: { color: 'rgba(255,255,255,0.6)' } },
  grid: { left: '3%', right: '4%', bottom: '10%', top: '5%', containLabel: true },
  xAxis: { type: 'category', data: statsData.value.chart_trend.dates, axisLabel: { color: 'rgba(255,255,255,0.6)' } },
  yAxis: [
    { type: 'value', name: '次数', nameTextStyle: { color: 'rgba(255,255,255,0.6)' }, axisLabel: { color: 'rgba(255,255,255,0.6)' }, splitLine: { lineStyle: { color: 'rgba(255,255,255,0.05)' } } },
    { type: 'value', name: '小时', splitLine: { show: false }, nameTextStyle: { color: 'rgba(255,255,255,0.6)' }, axisLabel: { color: 'rgba(255,255,255,0.6)' } }
  ],
  series: [
    { name: '播放次数', type: 'bar', data: statsData.value.chart_trend.counts, itemStyle: { color: '#8a2be2', borderRadius: [4, 4, 0, 0] }, barMaxWidth: 20 },
    { name: '时长(小时)', type: 'line', yAxisIndex: 1, data: statsData.value.chart_trend.hours, itemStyle: { color: '#63e2b7' }, smooth: true, areaStyle: { opacity: 0.1, color: '#63e2b7' } }
  ]
}));

const userChartOption = computed(() => ({
  tooltip: { trigger: 'axis', axisPointer: { type: 'shadow' }, backgroundColor: 'rgba(20, 25, 35, 0.85)', borderColor: 'rgba(255,255,255,0.1)', textStyle: { color: '#fff' } },
  grid: { left: '3%', right: '4%', bottom: '3%', top: '5%', containLabel: true },
  xAxis: { type: 'value', name: '小时', axisLabel: { color: 'rgba(255,255,255,0.6)' }, splitLine: { lineStyle: { color: 'rgba(255,255,255,0.05)' } } },
  yAxis: { type: 'category', data: statsData.value.chart_users.names, inverse: true, axisLabel: { color: 'rgba(255,255,255,0.8)' } }, 
  series: [{ name: '观看时长', type: 'bar', data: statsData.value.chart_users.hours, itemStyle: { color: '#70c0e8', borderRadius: [0, 4, 4, 0] }, label: { show: true, position: 'right', formatter: '{c} h', color: 'rgba(255,255,255,0.6)' }, barMaxWidth: 15 }]
}));

const getPosterUrl = (item) => `/image_proxy/Items/${item.id}/Images/Primary?maxWidth=300`;

const fetchData = async () => {
  loading.value = true;
  try {
    const res = await axios.get(`/api/portal/dashboard-stats?days=${timeRange.value}`);
    statsData.value = res.data;
  } catch (error) { message.error("加载数据失败"); } finally { loading.value = false; }
};

const openEmbyItem = (itemId) => {
  const embyServerUrl = statsData.value.emby_url;
  if (!embyServerUrl || !itemId) { message.warning("未配置 Emby 地址"); return; }
  const baseUrl = embyServerUrl.endsWith('/') ? embyServerUrl.slice(0, -1) : embyServerUrl;
  const serverId = statsData.value.emby_server_id;
  window.open(`${baseUrl}/web/index.html#!/item?id=${itemId}${serverId ? `&serverId=${serverId}` : ''}`, '_blank');
};

onMounted(() => { fetchData(); });
</script>

<style scoped>
.modular-page-container { padding: 24px; max-width: 1600px; margin: 0 auto; }
.page-header-module { margin-bottom: 24px; }
.greeting-title { font-size: 28px; font-weight: 700; margin: 0 0 8px 0; color: #fff; }
.greeting-subtitle { font-size: 14px; color: rgba(255,255,255,0.6); margin: 0; }

.stat-icon-glass {
  width: 48px; height: 48px; border-radius: 12px;
  background: rgba(255, 255, 255, 0.05);
  border: 1px solid rgba(255, 255, 255, 0.1);
  display: flex; align-items: center; justify-content: center;
}

.poster-wrapper {
  position: relative; border-radius: 8px; overflow: hidden; aspect-ratio: 2/3; 
  box-shadow: 0 4px 12px rgba(0,0,0,0.3); transition: transform 0.2s; cursor: pointer;
  background-color: rgba(0,0,0,0.2); border: 1px solid rgba(255, 255, 255, 0.05);
}
.poster-wrapper:hover { transform: translateY(-4px); box-shadow: 0 8px 24px rgba(0,0,0,0.5); }
.poster-img { width: 100%; height: 100%; display: block; }
:deep(.n-image img) { width: 100%; height: 100%; object-fit: cover; }

.poster-title {
  position: absolute; bottom: 0; left: 0; right: 0;
  background: linear-gradient(to top, rgba(0,0,0,0.9), transparent);
  color: white; padding: 20px 8px 8px; font-size: 12px;
  white-space: nowrap; overflow: hidden; text-overflow: ellipsis; text-align: center;
}
.rank-badge {
  position: absolute; top: 0; left: 0; width: 24px; height: 24px;
  background: rgba(0,0,0,0.6); color: white; font-weight: bold; font-size: 12px;
  display: flex; align-items: center; justify-content: center;
  border-bottom-right-radius: 8px; z-index: 2; backdrop-filter: blur(4px);
}
.rank-1 { background: rgba(255, 193, 7, 0.8); color: black; }
.rank-2 { background: rgba(173, 181, 189, 0.8); color: black; }
.rank-3 { background: rgba(205, 127, 50, 0.8); color: black; }

.play-count-badge {
  position: absolute; top: 4px; right: 4px;
  background: rgba(138, 43, 226, 0.8); color: white; font-size: 10px;
  padding: 2px 6px; border-radius: 4px; z-index: 2; backdrop-filter: blur(4px);
}

@media (max-width: 768px) {
  .modular-page-container { padding: 12px; }
  .greeting-title { font-size: 22px; }
}
</style>