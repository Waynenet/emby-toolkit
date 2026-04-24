<!-- src/components/DatabaseStats.vue -->
<template>
  <div class="modular-page-container">
    
    <div class="page-header-module" style="display: flex; justify-content: space-between; align-items: flex-end; flex-wrap: wrap; gap: 16px;">
      <div>
        <h1 class="greeting-title" style="display: flex; align-items: center; gap: 12px;">
          <n-icon color="#8a2be2"><StatsChart /></n-icon> 数据看板
        </h1>
        <p class="greeting-subtitle">了解您媒体库的核心数据统计与运行状态。</p>
      </div>
      <div class="filter-section">
        <n-button circle size="small" type="primary" ghost @click="fetchData" :loading="loading.core">
          <template #icon><n-icon><Refresh /></n-icon></template>
        </n-button>
      </div>
    </div>

    <n-spin :show="loading.core || loading.library || loading.system || loading.subscription || loading.rankings">
      
      <!-- 1. 顶部：媒体库分布 (左饼图，右4个核心数据) -->
      <n-grid :cols="1" lg:cols="3" :x-gap="24" :y-gap="24" responsive="screen" style="margin-bottom: 24px;">
        <n-gi span="1">
          <n-card :bordered="false" class="dashboard-card chart-module" style="height: 100%;">
            <template #header><span class="card-title">媒体库分布</span></template>
            <v-chart class="chart-container" :option="resolutionChartOptions" autoresize style="height: 220px; width: 100%;" />
          </n-card>
        </n-gi>
        <n-gi span="2">
          <n-grid :cols="2" m:cols="4" :x-gap="16" :y-gap="16" style="height: 100%;">
            <n-gi>
              <n-card :bordered="false" class="dashboard-card stat-module" style="justify-content: center;">
                <n-statistic label="电影总数" :value="stats.media_library.movies_in_library" />
              </n-card>
            </n-gi>
            <n-gi>
              <n-card :bordered="false" class="dashboard-card stat-module" style="justify-content: center;">
                <n-statistic label="剧集总数" :value="stats.media_library.series_in_library" />
              </n-card>
            </n-gi>
            <n-gi>
              <n-card :bordered="false" class="dashboard-card stat-module" style="justify-content: center;">
                <n-statistic label="单集总数" :value="stats.media_library.episodes_in_library" />
              </n-card>
            </n-gi>
            <n-gi>
              <n-card :bordered="false" class="dashboard-card stat-module" style="justify-content: center;">
                <n-statistic label="演员总数" :value="stats.system.actor_mappings_linked" />
              </n-card>
            </n-gi>
          </n-grid>
        </n-gi>
      </n-grid>

      <!-- 2. 中部：系统状态与自动化 (8个便当盒，一行4个) -->
      <n-grid :cols="2" m:cols="4" :x-gap="16" :y-gap="16" responsive="screen" style="margin-bottom: 24px;">
        <n-gi>
          <n-card :bordered="false" class="dashboard-card auto-task-block">
            <div class="auto-task-title">核心缓存</div>
            <div class="auto-task-stats">
              <span>媒体: <b>{{ stats.media_library.cached_total }}</b></span>
              <span>演员: <b>{{ stats.system.actor_mappings_total }}</b></span>
            </div>
          </n-card>
        </n-gi>
        <n-gi>
          <n-card :bordered="false" class="dashboard-card auto-task-block">
            <div class="auto-task-title">翻译缓存</div>
            <div class="auto-task-stats">
              <span>总计: <b>{{ stats.system.translation_cache_count }}</b> 条</span>
            </div>
          </n-card>
        </n-gi>
        <n-gi>
          <n-card :bordered="false" class="dashboard-card auto-task-block">
            <div class="auto-task-title">原生合集</div>
            <div class="auto-task-stats">
              <span>总: <b>{{ stats.subscriptions_card.native_collections.total }}</b></span>
              <span>缺: <b style="color: #e88080">{{ stats.subscriptions_card.native_collections.missing_items }}</b></span>
              <span>补: <b style="color: #f2c97d">{{ stats.subscriptions_card.native_collections.count }}</b></span>
            </div>
          </n-card>
        </n-gi>
        <n-gi>
          <n-card :bordered="false" class="dashboard-card auto-task-block">
            <div class="auto-task-title">自建合集</div>
            <div class="auto-task-stats">
              <span>总: <b>{{ stats.subscriptions_card.custom_collections.total }}</b></span>
              <span>缺: <b style="color: #e88080">{{ stats.subscriptions_card.custom_collections.missing_items }}</b></span>
              <span>补: <b style="color: #f2c97d">{{ stats.subscriptions_card.custom_collections.count }}</b></span>
            </div>
          </n-card>
        </n-gi>
        <n-gi>
          <n-card :bordered="false" class="dashboard-card auto-task-block">
            <div class="auto-task-title">智能追剧</div>
            <div class="auto-task-stats">
              <span>追: <b style="color: #63e2b7">{{ stats.subscriptions_card.watchlist.watching }}</b></span>
              <span>停: <b style="color: #f2c97d">{{ stats.subscriptions_card.watchlist.paused }}</b></span>
              <span>完: <b>{{ stats.subscriptions_card.watchlist.completed }}</b></span>
            </div>
          </n-card>
        </n-gi>
        <n-gi>
          <n-card :bordered="false" class="dashboard-card auto-task-block">
            <div class="auto-task-title">媒体洗版</div>
            <div class="auto-task-stats">
              <span>待处理: <b style="color: #f2c97d">{{ stats.subscriptions_card.resubscribe.pending }}</b></span>
            </div>
          </n-card>
        </n-gi>
        <n-gi>
          <n-card :bordered="false" class="dashboard-card auto-task-block">
            <div class="auto-task-title">MP 订阅配额</div>
            <div class="auto-task-stats">
              <span>已用: <b>{{ stats.subscriptions_card.quota.mp.consumed }}</b></span>
              <span>剩余: <b style="color: #63e2b7">{{ stats.subscriptions_card.quota.mp.available }}</b></span>
            </div>
          </n-card>
        </n-gi>
        <n-gi>
          <n-card :bordered="false" class="dashboard-card auto-task-block">
            <div class="auto-task-title">系统日志</div>
            <div class="auto-task-stats">
              <span>已处理: <b>{{ stats.system.processed_log_count }}</b></span>
              <span>待复核: <b style="color: #e88080">{{ stats.system.failed_log_count }}</b></span>
            </div>
          </n-card>
        </n-gi>
      </n-grid>

      <!-- 3. 底部：发布组排行 (左右并排) -->
      <n-grid :cols="1" lg:cols="2" :x-gap="24" :y-gap="24" responsive="screen">
        <!-- 左侧：今日排行 -->
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
                  <n-progress type="line" :percentage="(group.count / (stats.release_group_ranking[0]?.count || 1)) * 100" :show-indicator="false" :height="6" color="#8a2be2" />
                </div>
                <div class="ranking-count">{{ group.count }} 部</div>
              </div>
            </div>
          </n-card>
        </n-gi>

        <!-- 右侧：历史排行 -->
        <n-gi>
          <n-card :bordered="false" class="dashboard-card list-module" style="height: 100%;">
            <template #header><span class="card-title">历史总排行 Top 10</span></template>
            <div v-if="stats.historical_release_group_ranking.length === 0" style="padding: 40px 0; text-align: center;">
              <n-empty description="暂无历史数据" />
            </div>
            <div v-else class="ranking-list">
              <div v-for="(group, index) in stats.historical_release_group_ranking.slice(0, 10)" :key="group.release_group" class="ranking-item">
                <div class="ranking-index" :class="{'top-3': index < 3}">{{ index + 1 }}</div>
                <img :src="getIconPath(group.release_group)" class="site-icon" @error="handleIconError" />
                <div class="ranking-name">{{ group.release_group }}</div>
                <div class="ranking-bar-container">
                  <n-progress type="line" :percentage="(group.count / (stats.historical_release_group_ranking[0]?.count || 1)) * 100" :show-indicator="false" :height="6" color="#63e2b7" />
                </div>
                <div class="ranking-count">{{ group.count }} 部</div>
              </div>
            </div>
          </n-card>
        </n-gi>
      </n-grid>

    </n-spin>
  </div>
</template>

<script setup>
import { ref, onMounted, computed, reactive } from 'vue';
import axios from 'axios';
import { NGrid, NGi, NCard, NStatistic, NSpin, NIcon, NProgress, NEmpty, NButton } from 'naive-ui';
import { StatsChart, Refresh } from '@vicons/ionicons5';
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
  loading.rankings = true;
  try {
    const res = await axios.get(`/api/database/stats/rankings`);
    if (res.data.status === 'success') {
      stats.release_group_ranking = res.data.data.release_group_ranking;
      stats.historical_release_group_ranking = res.data.data.historical_release_group_ranking;
    }
  } catch (e) {} finally { loading.rankings = false; }
};

const fetchData = () => {
  fetchCore(); fetchLibrary(); fetchSystem(); fetchSubscription(); fetchRankings();
};

const resolutionChartOptions = computed(() => {
  const chartData = stats.media_library.resolution_stats || [];
  if (!chartData.length) {
    return { series: [{ type: 'pie', radius: ['40%', '70%'], data: [{ value: 0, name: '暂无数据' }], label: { show: false } }] };
  }
  return {
    color: ['#8a2be2', '#18a058', '#f0a020', '#d03050', '#999', '#73C0DE'],
    tooltip: { trigger: 'item', backgroundColor: 'rgba(20, 25, 35, 0.85)', borderColor: 'rgba(255,255,255,0.1)', textStyle: { color: '#fff' } },
    legend: { show: true, bottom: '0', textStyle: { color: 'var(--text-secondary)' } },
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
  fetchData();
});
</script>

<style scoped>
.modular-page-container { padding: 0; max-width: 1600px; margin: 0 auto; }
.page-header-module { margin-bottom: 24px; }
.greeting-title { font-size: 28px; font-weight: 700; margin: 0 0 8px 0; color: var(--text-primary); }
.greeting-subtitle { font-size: 14px; color: var(--text-secondary); margin: 0; }

.stat-module :deep(.n-statistic-value__content) { font-size: 32px; font-weight: bold; }
.stat-module { display: flex; align-items: center; }

/* 自动化任务便当盒 */
.auto-task-block {
  padding: 16px 20px;
}
.auto-task-title { font-size: 15px; font-weight: bold; color: var(--text-primary); margin-bottom: 12px; }
.auto-task-stats { display: flex; justify-content: space-between; font-size: 13px; color: var(--text-secondary); }
.auto-task-stats b { color: var(--text-primary); font-size: 16px; margin-left: 4px; }

/* 排行榜列表 */
.ranking-list { display: flex; flex-direction: column; gap: 12px; }
.ranking-item {
  display: flex; align-items: center; padding: 12px 16px;
  background: var(--glass-border); border-radius: 12px; border: 1px solid var(--glass-border-light);
}
.ranking-index { width: 24px; font-weight: bold; color: var(--text-secondary); }
.ranking-index.top-3 { color: #f2c97d; }
.site-icon { width: 20px; height: 20px; margin-right: 12px; border-radius: 4px; }
.ranking-name { width: 100px; font-weight: 600; color: var(--text-primary); white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.ranking-bar-container { flex: 1; margin: 0 16px; }
.ranking-count { width: 50px; text-align: right; font-size: 13px; color: var(--text-secondary); }

@media (max-width: 768px) {
  .modular-page-container { padding: 0; }
  .greeting-title { font-size: 22px; }
  .ranking-name { width: 80px; }
}
</style>