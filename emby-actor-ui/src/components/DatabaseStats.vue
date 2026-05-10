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
        <!-- 按钮绑定全局 loading 状态 -->
        <n-button circle size="small" type="primary" ghost @click="fetchData" :loading="isAnyLoading">
          <template #icon><n-icon><Refresh /></n-icon></template>
        </n-button>
      </div>
    </div>

    <!-- ★★★ 1. 顶部核心数据区 (左：分布图+媒体数量，右：系统状态) ★★★ -->
    <n-grid cols="1 m:2" :x-gap="16" :y-gap="16" responsive="screen" style="margin-bottom: 16px;">
      <!-- 左侧：图表与媒体库数量融合模块 -->
      <n-gi>
        <n-card :bordered="false" class="dashboard-card tint-blue" style="height: 100%; display: flex; flex-direction: column;">
          <template #header><span class="card-title">媒体库分布</span></template>
          
          <!-- 图表区 -->
          <div v-if="loading.library" class="library-chart-wrapper" style="display: flex; justify-content: center; align-items: center;">
            <n-skeleton circle :width="120" :height="120" />
          </div>
          <v-chart v-else class="chart-container library-chart-wrapper" :option="resolutionChartOptions" autoresize style="width: 100%;" />

          <!-- 融合的媒体库数据 -->
          <div class="integrated-media-stats">
            <div class="stat-item">
              <n-skeleton v-if="loading.library" text style="width: 40px; margin: auto;" />
              <div v-else class="stat-val">{{ stats.media_library.movies_in_library }}</div>
              <div class="stat-label">电影</div>
            </div>
            <n-divider vertical style="height: 30px; margin: 0 12px;" />
            <div class="stat-item">
              <n-skeleton v-if="loading.library" text style="width: 40px; margin: auto;" />
              <div v-else class="stat-val">{{ stats.media_library.series_in_library }}</div>
              <div class="stat-label">剧集</div>
            </div>
            <n-divider vertical style="height: 30px; margin: 0 12px;" />
            <div class="stat-item">
              <n-skeleton v-if="loading.library" text style="width: 40px; margin: auto;" />
              <div v-else class="stat-val">{{ stats.media_library.episodes_in_library }}</div>
              <div class="stat-label">总集数</div>
            </div>
          </div>
        </n-card>
      </n-gi>
      
      <!-- 右侧：基础缓存、媒体处理、MP配额、洗版任务 (2x2) -->
      <n-gi>
        <n-grid cols="1 s:2" :x-gap="16" :y-gap="16" responsive="screen" style="height: 100%;">
          <n-gi>
            <n-card :bordered="false" class="dashboard-card auto-task-block tint-orange">
              <div class="auto-task-title">基础缓存</div>
              <div v-if="loading.core || loading.system" class="auto-task-stats"><n-skeleton text :repeat="3" /></div>
              <div v-else class="auto-task-stats">
                <span>媒体缓存数: <b>{{ stats.media_library.cached_total }}</b></span>
                <span>翻译缓存数: <b>{{ stats.system.translation_cache_count }}</b></span>
              </div>
            </n-card>
          </n-gi>
          <n-gi>
            <n-card :bordered="false" class="dashboard-card auto-task-block tint-red">
              <div class="auto-task-title">媒体处理</div>
              <div v-if="loading.system" class="auto-task-stats"><n-skeleton text :repeat="2" /></div>
              <div v-else class="auto-task-stats">
                <span>已处理: <b>{{ stats.system.processed_log_count }}</b></span>
                <span>待复核: <b style="color: #ffcccc">{{ stats.system.failed_log_count }}</b></span>
              </div>
            </n-card>
          </n-gi>
          <n-gi>
            <n-card :bordered="false" class="dashboard-card auto-task-block tint-purple">
              <div class="auto-task-title">MP 订阅配额</div>
              <div v-if="loading.subscription" class="auto-task-stats"><n-skeleton text :repeat="2" /></div>
              <div v-else class="auto-task-stats">
                <span>今日已用: <b>{{ stats.subscriptions_card.quota.mp.consumed }}</b></span>
                <span>今日剩余: <b style="color: #c1f0c1">{{ stats.subscriptions_card.quota.mp.available }}</b></span>
              </div>
            </n-card>
          </n-gi>
          <n-gi>
            <n-card :bordered="false" class="dashboard-card auto-task-block tint-blue">
              <div class="auto-task-title">洗版任务</div>
              <div v-if="loading.subscription" class="auto-task-stats"><n-skeleton text :repeat="1" /></div>
              <div v-else class="auto-task-stats">
                <span>待洗版: <b style="color: #ffe4b5">{{ stats.subscriptions_card.resubscribe.pending }}</b></span>
              </div>
            </n-card>
          </n-gi>
        </n-grid>
      </n-gi>
    </n-grid>

    <!-- ★★★ 2. 订阅与合集数据模块 (一行四个) ★★★ -->
    <n-grid cols="1 s:2 m:4" :x-gap="16" :y-gap="16" responsive="screen" style="margin-bottom: 16px;">
      
      <n-gi>
        <n-card :bordered="false" class="dashboard-card auto-task-block tint-purple">
          <div class="auto-task-title">智能追剧</div>
          <div v-if="loading.subscription" class="auto-task-stats"><n-skeleton text :repeat="3" /></div>
          <div v-else class="auto-task-stats">
            <span>追剧中: <b>{{ stats.subscriptions_card.watchlist.watching }}</b></span>
            <span>已暂停: <b style="color: #ffe4b5">{{ stats.subscriptions_card.watchlist.paused }}</b></span>
            <span>已完结: <b style="color: #c1f0c1">{{ stats.subscriptions_card.watchlist.completed }}</b></span>
          </div>
        </n-card>
      </n-gi>

      <n-gi>
        <n-card :bordered="false" class="dashboard-card auto-task-block tint-blue">
          <div class="auto-task-title">演员订阅</div>
          <div v-if="loading.subscription" class="auto-task-stats"><n-skeleton text :repeat="2" /></div>
          <div v-else class="auto-task-stats">
            <span>已订阅: <b>{{ stats.subscriptions_card.actors.subscriptions }}</b></span>
            <span>作品入库: <b style="color: #c1f0c1">{{ stats.subscriptions_card.actors.tracked_in_library }}</b></span>
          </div>
        </n-card>
      </n-gi>

      <n-gi>
        <n-card :bordered="false" class="dashboard-card auto-task-block tint-green">
          <div class="auto-task-title">原生合集</div>
          <div v-if="loading.subscription" class="auto-task-stats"><n-skeleton text :repeat="3" /></div>
          <div v-else class="auto-task-stats">
            <span>总数: <b>{{ stats.subscriptions_card.native_collections.total }}</b></span>
            <span>待补: <b style="color: #ffe4b5">{{ stats.subscriptions_card.native_collections.count }}</b></span>
            <span>缺失: <b style="color: #ffcccc">{{ stats.subscriptions_card.native_collections.missing_items }}</b></span>
          </div>
        </n-card>
      </n-gi>

      <n-gi>
        <n-card :bordered="false" class="dashboard-card auto-task-block tint-orange">
          <div class="auto-task-title">自建合集</div>
          <div v-if="loading.subscription" class="auto-task-stats"><n-skeleton text :repeat="3" /></div>
          <div v-else class="auto-task-stats">
            <span>总数: <b>{{ stats.subscriptions_card.custom_collections.total }}</b></span>
            <span>待补: <b style="color: #ffe4b5">{{ stats.subscriptions_card.custom_collections.count }}</b></span>
            <span>缺失: <b style="color: #ffcccc">{{ stats.subscriptions_card.custom_collections.missing_items }}</b></span>
          </div>
        </n-card>
      </n-gi>

    </n-grid>

    <!-- ★★★ 3. 发布组排行 (底部并列) ★★★ -->
    <n-grid cols="1 m:2" :x-gap="16" :y-gap="16" responsive="screen">
      <!-- 左侧：今日排行 -->
      <n-gi>
        <n-card :bordered="false" class="dashboard-card list-module" style="height: 100%;">
          <template #header><span class="card-title">今日发布组 Top 5</span></template>
          
          <!-- 排行榜骨架屏 -->
          <div v-if="loading.rankings" class="ranking-list">
            <div v-for="i in 5" :key="i" class="ranking-item skeleton-item">
              <n-skeleton text style="width: 24px; margin-right: 12px;" />
              <n-skeleton circle size="20" style="margin-right: 12px;" />
              <n-skeleton text style="flex: 1;" />
            </div>
          </div>
          
          <div v-else-if="stats.release_group_ranking.length === 0" style="padding: 40px 0; text-align: center; margin-top: 16px;">
            <n-empty description="今日暂无入库" />
          </div>
          
          <div v-else class="ranking-list">
            <div v-for="(group, index) in stats.release_group_ranking.slice(0, 5)" :key="group.release_group" class="ranking-item">
              <div class="ranking-index" :class="{'top-3': index < 3}">{{ index + 1 }}</div>
              <img :src="getIconPath(group.release_group)" class="site-icon" @error="handleIconError" />
              <div class="ranking-name">{{ group.release_group }}</div>
              <div class="ranking-bar-container">
                <n-progress type="line" :percentage="(group.count / (stats.release_group_ranking[0]?.count || 1)) * 100" :show-indicator="false" :height="6" color="#8a2be2" rail-color="rgba(150, 150, 150, 0.2)" />
              </div>
              <div class="ranking-count">{{ group.count }} 部</div>
            </div>
          </div>
        </n-card>
      </n-gi>

      <!-- 右侧：历史排行 -->
      <n-gi>
        <n-card :bordered="false" class="dashboard-card list-module" style="height: 100%;">
          <template #header><span class="card-title">历史总排行 Top 5</span></template>
          
          <!-- 排行榜骨架屏 -->
          <div v-if="loading.rankings" class="ranking-list">
            <div v-for="i in 5" :key="i" class="ranking-item skeleton-item">
              <n-skeleton text style="width: 24px; margin-right: 12px;" />
              <n-skeleton circle size="20" style="margin-right: 12px;" />
              <n-skeleton text style="flex: 1;" />
            </div>
          </div>

          <div v-else-if="stats.historical_release_group_ranking.length === 0" style="padding: 40px 0; text-align: center; margin-top: 16px;">
            <n-empty description="暂无历史数据" />
          </div>
          
          <div v-else class="ranking-list">
            <div v-for="(group, index) in stats.historical_release_group_ranking.slice(0, 5)" :key="group.release_group" class="ranking-item">
              <div class="ranking-index" :class="{'top-3': index < 3}">{{ index + 1 }}</div>
              <img :src="getIconPath(group.release_group)" class="site-icon" @error="handleIconError" />
              <div class="ranking-name">{{ group.release_group }}</div>
              <div class="ranking-bar-container">
                <n-progress type="line" :percentage="(group.count / (stats.historical_release_group_ranking[0]?.count || 1)) * 100" :show-indicator="false" :height="6" color="#8a2be2" rail-color="rgba(150, 150, 150, 0.2)" />
              </div>
              <div class="ranking-count">{{ group.count }} 部</div>
            </div>
          </div>
        </n-card>
      </n-gi>
    </n-grid>

  </div>
</template>

<script setup>
import { ref, onMounted, computed, reactive } from 'vue';
import axios from 'axios';
import { NGrid, NGi, NCard, NIcon, NProgress, NEmpty, NButton, NSkeleton, NDivider } from 'naive-ui'; // 新增导入 NDivider
import { StatsChart, Refresh } from '@vicons/ionicons5';
import { use } from 'echarts/core';
import { CanvasRenderer } from 'echarts/renderers';
import { PieChart } from 'echarts/charts';
import { TitleComponent, TooltipComponent, LegendComponent } from 'echarts/components';
import VChart from 'vue-echarts';

use([ CanvasRenderer, PieChart, TitleComponent, TooltipComponent, LegendComponent ]);

// 拆分的 loading 状态
const loading = reactive({ core: true, library: true, system: true, subscription: true, rankings: true });

// 全局 Loading 计算属性，用于刷新按钮
const isAnyLoading = computed(() => {
  return loading.core || loading.library || loading.system || loading.subscription || loading.rankings;
});

const stats = reactive({
  media_library: { cached_total: 0, mediainfo_backed_up_total: 0, mediainfo_hits_total: 0, movies_in_library: 0, series_in_library: 0, episodes_in_library: 0, resolution_stats: [] },
  system: { translation_cache_count: 0, processed_log_count: 0, failed_log_count: 0 },
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
  loading.core = true;
  try {
    const res = await axios.get('/api/database/stats/core');
    if (res.data.status === 'success') {
      Object.assign(stats.media_library, { cached_total: res.data.data.media_cached_total });
    }
  } catch (e) {} finally { loading.core = false; }
};

const fetchLibrary = async () => {
  loading.library = true;
  try {
    const res = await axios.get('/api/database/stats/library');
    if (res.data.status === 'success') {
      // 防止并发请求导致数据被覆盖：先提取 library 数据中可能为空的 cached_total
      const { cached_total, ...otherLibraryData } = res.data.data;
      
      // 合并其他库数据
      Object.assign(stats.media_library, otherLibraryData);
      
      // 只有当 library 接口确实返回了有效的缓存数时，才允许覆盖
      if (cached_total !== undefined && cached_total !== null) {
        stats.media_library.cached_total = cached_total;
      }
    }
  } catch (e) {
    console.error("获取媒体库数据失败", e);
  } finally { 
    loading.library = false; 
  }
};
const fetchSystem = async () => {
  loading.system = true;
  try {
    const res = await axios.get('/api/database/stats/system');
    if (res.data.status === 'success') Object.assign(stats.system, res.data.data);
  } catch (e) {} finally { loading.system = false; }
};
const fetchSubscription = async () => {
  loading.subscription = true;
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
    return { series: [{ type: 'pie', radius: ['45%', '72%'], center: ['50%', '40%'], data: [{ value: 0, name: '暂无数据' }], label: { show: false } }] };
  }
  return {
    color: ['#8a2be2', '#18a058', '#f0a020', '#d03050', '#999', '#73C0DE'],
    tooltip: { trigger: 'item', backgroundColor: 'rgba(20, 25, 35, 0.85)', borderColor: 'rgba(255,255,255,0.1)', textStyle: { color: '#fff' } },
    legend: { show: true, bottom: '0', textStyle: { color: 'var(--text-primary)' } },
    series: [{
      type: 'pie',
      radius: ['45%', '72%'], // 恢复大半径，饱满醒目
      center: ['50%', '40%'], // 中心点偏上，留出底部图例空间
      itemStyle: { borderRadius: 8, borderColor: 'rgba(255,255,255,0.2)', borderWidth: 2 },
      label: { show: false },
      data: chartData.map(item => ({ value: item.count, name: item.resolution || '未知' }))
    }]
  };
});

const getIconPath = (groupName) => groupName ? `/icons/site/${groupName}.png` : '';
const handleIconError = (e) => {
  const img = e.target;
  const currentSrc = img.src;
  const defaultIcon = '/icons/site/pt.ico';
  if (currentSrc.match(/\.png($|\?)/i)) {
    img.src = currentSrc.replace(/\.png/i, '.ico');
    return;
  }
  if (currentSrc.includes('pt.ico')) {
    img.style.display = 'none';
  } else {
    img.src = defaultIcon;
    img.style.display = 'inline-block';
  }
};

onMounted(() => {
  fetchData();
});
</script>

<style scoped>
.modular-page-container { padding: 24px; max-width: 1600px; margin: 0 auto; }
.page-header-module { margin-bottom: 24px; }
.greeting-title { font-size: 28px; font-weight: 700; margin: 0 0 8px 0; color: var(--text-primary); }
.greeting-subtitle { font-size: 14px; color: var(--text-secondary); margin: 0; }

/* 融合后的媒体库数据统计样式 */
.integrated-media-stats {
  display: flex;
  justify-content: space-around;
  align-items: center;
  margin-top: 12px;
  padding-top: 16px;
  border-top: 1px dashed var(--glass-border-light, rgba(150, 150, 150, 0.2));
}
.stat-item { text-align: center; width: 33%; }
.stat-val { font-size: 22px; font-weight: bold; color: var(--text-primary); line-height: 1.2; }
.stat-label { font-size: 13px; color: var(--text-secondary); margin-top: 4px; }

/* PC端稍微加高一点，让大图更舒展 */
.library-chart-wrapper {
  height: 220px; 
  margin-top: 8px;
}

.auto-task-block {
  padding: 16px;
  height: 100%;
  display: flex;
  flex-direction: column;
  justify-content: center;
}
.auto-task-title { font-size: 15px; font-weight: bold; color: var(--text-primary); margin-bottom: 12px; }
.auto-task-stats { display: flex; flex-direction: column; gap: 6px; font-size: 13px; color: var(--text-primary); opacity: 0.9; }
.auto-task-stats span { display: flex; justify-content: space-between; }
.auto-task-stats b { color: var(--text-primary); font-size: 14px; font-weight: 900; }

/* 排行榜增加了 margin-top 让它与标题产生适当间距 */
.ranking-list { display: flex; flex-direction: column; gap: 12px; margin-top: 16px; }
.ranking-item {
  display: flex; align-items: center; padding: 12px 16px;
  background: var(--glass-border); border-radius: 12px; border: 1px solid var(--glass-border-light);
}
.skeleton-item { border: 1px dashed rgba(150, 150, 150, 0.2); }
.ranking-index { width: 24px; font-weight: bold; color: var(--text-secondary); flex-shrink: 0; }
.ranking-index.top-3 { color: #fff; text-shadow: 0 0 8px rgba(255,255,255,0.8); }
.site-icon { width: 20px; height: 20px; margin-right: 12px; border-radius: 4px; flex-shrink: 0; }

.ranking-name { width: 65px; font-weight: 600; color: var(--text-primary); white-space: nowrap; overflow: hidden; text-overflow: ellipsis; flex-shrink: 0; }
.ranking-bar-container { flex: 1; margin: 0 12px 0 4px; min-width: 50px; }
.ranking-count { width: 50px; text-align: right; font-size: 13px; color: var(--text-secondary); flex-shrink: 0; }

@media (max-width: 768px) {
  .modular-page-container { padding: 12px; }
  .greeting-title { font-size: 22px; }
  
  .integrated-media-stats { padding-top: 12px; margin-top: 8px; }
  .stat-val { font-size: 18px; }
  
  .ranking-item { padding: 10px 12px; }
  .ranking-index { width: 18px; font-size: 13px; }
  .site-icon { margin-right: 8px; width: 16px; height: 16px; }
  
  .ranking-name { width: 55px; font-size: 13px; }
  .ranking-bar-container { margin: 0 8px 0 2px; }
  .ranking-count { width: 45px; font-size: 12px; }

  .library-chart-wrapper {
    height: 260px; /* 给足260px高度，完美容纳大饼图 + 2行图例 */
  }
}
</style>