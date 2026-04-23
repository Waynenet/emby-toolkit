<!-- src/components/DatabaseStats.vue -->
<template>
  <div class="modular-page-container">
    
    <div class="page-header-module">
      <h1 class="greeting-title">数据看板</h1>
      <p class="greeting-subtitle">了解您媒体库的核心数据统计与运行状态。</p>
    </div>
    
    <!-- 1. 核心数据 (响应式网格: 手机2列，电脑4列) -->
    <n-grid :x-gap="16" :y-gap="16" cols="2 m:4" responsive="screen" style="margin-bottom: 24px;">
      <n-gi>
        <n-card :bordered="false" class="dashboard-card stat-module">
          <n-statistic label="已缓存媒体" :value="stats.media_library.cached_total" />
        </n-card>
      </n-gi>
      <n-gi>
        <n-card :bordered="false" class="dashboard-card stat-module">
          <n-statistic label="已归档演员" :value="stats.system.actor_mappings_total" />
        </n-card>
      </n-gi>
      <n-gi>
        <n-card :bordered="false" class="dashboard-card stat-module">
          <n-statistic label="追剧中" :value="stats.subscriptions_card.watchlist.watching" style="--n-value-text-color: #63e2b7" />
        </n-card>
      </n-gi>
      <n-gi>
        <n-card :bordered="false" class="dashboard-card stat-module">
          <n-statistic label="待洗版" :value="stats.subscriptions_card.resubscribe.pending" style="--n-value-text-color: #f2c97d" />
        </n-card>
      </n-gi>
    </n-grid>

    <!-- 2. 主体图表与列表 (响应式网格: 手机1列，电脑2列) -->
    <n-grid :x-gap="24" :y-gap="24" cols="1 lg:2" responsive="screen">
      
      <!-- 左侧：媒体库分布图 -->
      <n-gi>
        <n-card :bordered="false" class="dashboard-card chart-module" style="height: 100%;">
          <template #header><span class="card-title">媒体库分布</span></template>
          
          <v-chart class="chart-container" :option="resolutionChartOptions" autoresize style="height: 260px; width: 100%;" />
          
          <n-grid :cols="4" :x-gap="8" :y-gap="12" style="text-align: center; margin-top: 16px; background: rgba(0,0,0,0.2); padding: 16px; border-radius: 12px;">
            <n-gi>
              <div class="mini-stat-val">{{ stats.media_library.movies_in_library }}</div>
              <div class="mini-stat-label">电影</div>
            </n-gi>
            <n-gi>
              <div class="mini-stat-val">{{ stats.media_library.series_in_library }}</div>
              <div class="mini-stat-label">剧集</div>
            </n-gi>
            <n-gi>
              <div class="mini-stat-val">{{ stats.media_library.episodes_in_library }}</div>
              <div class="mini-stat-label">总集数</div>
            </n-gi>
            <n-gi>
              <div class="mini-stat-val">{{ stats.system.actor_mappings_linked }}</div>
              <div class="mini-stat-label">演员</div>
            </n-gi>
          </n-grid>
        </n-card>
      </n-gi>

      <!-- 右侧：发布组排行 -->
      <n-gi>
        <n-card :bordered="false" class="dashboard-card list-module" style="height: 100%;">
          <template #header><span class="card-title">今日发布组 Top 10</span></template>
          
          <div v-if="stats.release_group_ranking.length === 0" style="padding: 40px 0; text-align: center;">
            <n-empty description="今日暂无入库" />
          </div>
          <div v-else class="ranking-list">
            <div v-for="(group, index) in stats.release_group_ranking.slice(0, 10)" :key="group.release_group" class="ranking-item">
              <div class="ranking-index" :class="{'top-3': index < 3}">{{ index + 1 }}</div>
              <img :src="getIconPath(group.release_group)" class="site-icon" @error="handleIconError" />
              <div class="ranking-name">{{ group.release_group }}</div>
              <div class="ranking-bar-container">
                <n-progress
                  type="line"
                  :percentage="(group.count / (stats.release_group_ranking[0]?.count || 1)) * 100"
                  :show-indicator="false"
                  :height="6"
                  color="#8a2be2"
                />
              </div>
              <div class="ranking-count">{{ group.count }} 部</div>
            </div>
          </div>
        </n-card>
      </n-gi>

      <!-- 底部：自动化任务状态 -->
      <n-gi span="1 lg:2">
        <n-card :bordered="false" class="dashboard-card action-module">
          <template #header><span class="card-title">自动化任务概览</span></template>
          <n-grid :cols="1" s:cols="3" :x-gap="16" :y-gap="16" responsive="screen">
            <n-gi>
              <div class="auto-task-block">
                <div class="auto-task-title">原生合集</div>
                <div class="auto-task-stats">
                  <span>总数: <b>{{ stats.subscriptions_card.native_collections.total }}</b></span>
                  <span>待补: <b style="color: #f2c97d">{{ stats.subscriptions_card.native_collections.count }}</b></span>
                </div>
              </div>
            </n-gi>
            <n-gi>
              <div class="auto-task-block">
                <div class="auto-task-title">自建合集</div>
                <div class="auto-task-stats">
                  <span>总数: <b>{{ stats.subscriptions_card.custom_collections.total }}</b></span>
                  <span>待补: <b style="color: #f2c97d">{{ stats.subscriptions_card.custom_collections.count }}</b></span>
                </div>
              </div>
            </n-gi>
            <n-gi>
              <div class="auto-task-block">
                <div class="auto-task-title">MP 订阅配额</div>
                <div class="auto-task-stats">
                  <span>已用: <b>{{ stats.subscriptions_card.quota.mp.consumed }}</b></span>
                  <span>剩余: <b style="color: #63e2b7">{{ stats.subscriptions_card.quota.mp.available }}</b></span>
                </div>
              </div>
            </n-gi>
          </n-grid>
        </n-card>
      </n-gi>

    </n-grid>
  </div>
</template>

<script setup>
// 这里的 script 逻辑完全保持你原来的代码不变
import { ref, onMounted, onUnmounted, computed, reactive } from 'vue';
import axios from 'axios';
import { NGrid, NGi, NCard, NStatistic, NSpin, NIcon, NSpace, NDivider, NIconWrapper, NProgress, NEmpty } from 'naive-ui';
import { use } from 'echarts/core';
import { CanvasRenderer } from 'echarts/renderers';
import { PieChart } from 'echarts/charts';
import { TitleComponent, TooltipComponent, LegendComponent } from 'echarts/components';
import VChart from 'vue-echarts';

use([ CanvasRenderer, PieChart, TitleComponent, TooltipComponent, LegendComponent ]);

const loading = reactive({ core: true, library: true, system: true, subscription: true, rankings: true });

const stats = reactive({
  media_library: { cached_total: 0, mediainfo_backed_up_total: 0, mediainfo_hits_total: 0, movies_in_library: 0, series_in_library: 0, episodes_in_library: 0, resolution_stats: [] },
  system: { actor_mappings_total: 0, actor_mappings_linked: 0, actor_mappings_unlinked: 0, translation_cache_count: 0, processed_log_count: 0, failed_log_count: 0 },
  subscriptions_card: {
    watchlist: { watching: 0, paused: 0, completed: 0 },
    actors: { subscriptions: 0, tracked_total: 0, tracked_in_library: 0 },
    resubscribe: { pending: 0 },
    native_collections: { total: 0, count: 0, missing_items: 0 },
    custom_collections: { total: 0, count: 0, missing_items: 0 },
    quota: { mp: { available: 0, consumed: 0 } }
  },
  release_group_ranking: [],
  historical_release_group_ranking: []
});

const fetchCore = async () => {
  try {
    const res = await axios.get('/api/database/stats/core');
    if (res.data.status === 'success') {
      Object.assign(stats.media_library, { cached_total: res.data.data.media_cached_total });
      Object.assign(stats.system, { actor_mappings_total: res.data.data.actor_mappings_total });
    }
  } catch (e) {} finally { loading.core = false; }
};
const fetchLibrary = async () => {
  try {
    const res = await axios.get('/api/database/stats/library');
    if (res.data.status === 'success') Object.assign(stats.media_library, res.data.data);
  } catch (e) {} finally { loading.library = false; }
};
const fetchSystem = async () => {
  try {
    const res = await axios.get('/api/database/stats/system');
    if (res.data.status === 'success') Object.assign(stats.system, res.data.data);
  } catch (e) {} finally { loading.system = false; }
};
const fetchSubscription = async () => {
  try {
    const res = await axios.get('/api/database/stats/subscription');
    if (res.data.status === 'success') Object.assign(stats.subscriptions_card, res.data.data);
  } catch (e) {} finally { loading.subscription = false; }
};
const fetchRankings = async () => {
  try {
    const res = await axios.get('/api/database/stats/rankings');
    if (res.data.status === 'success') {
      stats.release_group_ranking = res.data.data.release_group_ranking;
      stats.historical_release_group_ranking = res.data.data.historical_release_group_ranking;
    }
  } catch (e) {} finally { loading.rankings = false; }
};

const resolutionChartOptions = computed(() => {
  const chartData = stats.media_library.resolution_stats || [];
  if (!chartData.length) {
    return { series: [{ type: 'pie', radius: ['40%', '70%'], data: [{ value: 0, name: '暂无数据' }], label: { show: false } }] };
  }
  return {
    color: ['#8a2be2', '#18a058', '#f0a020', '#d03050', '#999', '#73C0DE'],
    tooltip: { trigger: 'item', backgroundColor: 'rgba(20, 25, 35, 0.85)', borderColor: 'rgba(255,255,255,0.1)', textStyle: { color: '#fff' } },
    legend: { show: true, bottom: '0', textStyle: { color: 'rgba(255,255,255,0.6)' } },
    series: [{
      type: 'pie',
      radius: ['45%', '75%'],
      center: ['50%', '40%'],
      itemStyle: { borderRadius: 8, borderColor: 'rgba(20,25,35,0.8)', borderWidth: 2 },
      label: { show: false },
      data: chartData.map(item => ({ value: item.count, name: item.resolution || '未知' }))
    }]
  };
});

const getIconPath = (groupName) => groupName ? `/icons/site/${groupName}.png` : '';
const handleIconError = (e) => { e.target.style.display = 'none'; };

onMounted(() => {
  fetchCore(); fetchLibrary(); fetchSystem(); fetchSubscription(); fetchRankings();
});
</script>

<style scoped>
/* 模块化页面基础容器 */
.modular-page-container {
  padding: 24px;
  max-width: 1600px;
  margin: 0 auto;
}

.page-header-module {
  margin-bottom: 24px;
}
.greeting-title {
  font-size: 28px;
  font-weight: 700;
  margin: 0 0 8px 0;
  color: #fff;
}
.greeting-subtitle {
  font-size: 14px;
  color: rgba(255,255,255,0.6);
  margin: 0;
}

/* 统计小模块 */
.stat-module :deep(.n-statistic-value__content) {
  font-size: 28px;
  font-weight: bold;
}

/* 迷你统计 */
.mini-stat-val { font-size: 18px; font-weight: bold; color: #fff; }
.mini-stat-label { font-size: 12px; color: rgba(255,255,255,0.5); }

/* 排行榜列表 */
.ranking-list {
  display: flex;
  flex-direction: column;
  gap: 12px;
}
.ranking-item {
  display: flex;
  align-items: center;
  padding: 12px 16px;
  background: rgba(0, 0, 0, 0.2);
  border-radius: 12px;
  border: 1px solid rgba(255, 255, 255, 0.05);
}
.ranking-index {
  width: 24px;
  font-weight: bold;
  color: rgba(255,255,255,0.4);
}
.ranking-index.top-3 { color: #f2c97d; }
.site-icon { width: 20px; height: 20px; margin-right: 12px; border-radius: 4px; }
.ranking-name { width: 100px; font-weight: 600; color: #fff; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.ranking-bar-container { flex: 1; margin: 0 16px; }
.ranking-count { width: 50px; text-align: right; font-size: 13px; color: rgba(255,255,255,0.6); }

/* 自动化任务块 */
.auto-task-block {
  background: rgba(0, 0, 0, 0.2);
  padding: 16px;
  border-radius: 12px;
  border: 1px solid rgba(255, 255, 255, 0.05);
}
.auto-task-title {
  font-size: 14px;
  font-weight: bold;
  color: #fff;
  margin-bottom: 12px;
}
.auto-task-stats {
  display: flex;
  justify-content: space-between;
  font-size: 13px;
  color: rgba(255,255,255,0.6);
}
.auto-task-stats b { color: #fff; font-size: 16px; margin-left: 4px; }

/* 手机端适配 */
@media (max-width: 768px) {
  .modular-page-container { padding: 12px; }
  .greeting-title { font-size: 22px; }
  .ranking-name { width: 80px; }
}
</style>