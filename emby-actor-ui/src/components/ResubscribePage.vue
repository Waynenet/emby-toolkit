<!-- src/components/ResubscribePage.vue -->
<template>
  <div content-style="padding: 24px;" class="page-container">
    <div class="resubscribe-page">
      <n-page-header>
        <template #title>
          <n-space align="center">
            <span>媒体整理</span>
            <n-tag v-if="allItems.length > 0" type="info" round :bordered="false" size="small">
              {{ filteredItems.length }} / {{ allItems.length }} 项
            </n-tag>
          </n-space>
        </template>
        <n-alert title="操作提示" type="info" style="margin-top: 24px;">
          <li>先设定规则，然后点击刷新按钮扫描全库。</li>
          <li>点击 <b>“整理”</b> 按钮将根据匹配到的规则执行操作：可能是 <b>洗版订阅</b>，也可能是 <b>直接删除</b>（取决于规则设定）。</li>
          <li>按住 Shift 键可以进行多选。</li>
        </n-alert>
        <template #extra>
          <!-- ★ 优化：加上 wrap 允许小屏幕换行 -->
          <n-space align="center" wrap class="header-actions">
            <n-dropdown
              trigger="click"
              :options="batchActions"
              @select="handleBatchAction"
            >
              <n-button size="small">
                批量操作 ({{ selectedItems.size }})
              </n-button>
            </n-dropdown>
          
            <n-radio-group v-model:value="filter" size="small" class="status-radio-group">
              <n-radio-button value="all">全部</n-radio-button>
              <n-radio-button value="needed">需处理</n-radio-button>
              <n-radio-button value="subscribed">处理中</n-radio-button>
              <n-radio-button value="ignored">已忽略</n-radio-button>
            </n-radio-group>
          
            <n-button size="small" @click="showSettingsModal = true">规则设定</n-button>
          
            <n-button size="small" type="warning" @click="triggerResubscribeAll" :loading="isTaskRunning('全库媒体洗版')">
              一键整理全部
            </n-button>
          
            <n-tooltip trigger="hover">
              <template #trigger>
                <n-button size="small" type="primary" @click="triggerRefreshStatus" :loading="isTaskRunning('刷新媒体整理')" circle>
                  <template #icon><n-icon :component="SyncOutline" /></template>
                </n-button>
              </template>
              扫描媒体库
            </n-tooltip>
          </n-space>
        </template>
      </n-page-header>

      <!-- ★ 优化：筛选栏加上自定义类 filter-bar -->
      <div class="filter-bar">
        <n-input
          v-model:value="searchQuery"
          placeholder="按名称搜索..."
          clearable
          class="filter-input-search"
        />
        <div class="filter-options">
          <n-select
            v-model:value="mediaTypeFilter"
            :options="mediaTypeOptions"
            placeholder="按类型筛选"
            class="filter-select-type"
          />
          <n-select
            v-model:value="ruleFilter"
            :options="ruleOptions"
            placeholder="按规则筛选"
            class="filter-select-rule"
          />
          <n-select
            v-model:value="sortBy"
            :options="sortOptions"
            class="filter-select-sort"
          />
          <n-button-group class="filter-sort-btns">
            <n-button @click="sortOrder = 'asc'" :type="sortOrder === 'asc' ? 'primary' : 'default'">
              <template #icon><n-icon :component="ArrowUpIcon" /></template>
              升序
            </n-button>
            <n-button @click="sortOrder = 'desc'" :type="sortOrder === 'desc' ? 'primary' : 'default'">
              <template #icon><n-icon :component="ArrowDownIcon" /></template>
              降序
            </n-button>
          </n-button-group>
        </div>
      </div>

      <n-divider />

      <div v-if="isLoading" class="center-container"><n-spin size="large" /></div>
      <div v-else-if="error" class="center-container"><n-alert title="加载错误" type="error">{{ error }}</n-alert></div>
      <div v-else-if="displayedItems.length > 0">
      
      <!-- ★★★ Grid 容器 ★★★ -->
      <div class="responsive-grid">
        <div 
          v-for="(item, index) in displayedItems" 
          :key="item.item_id" 
          class="grid-item"
        >
          <n-card 
            class="dashboard-card series-card" 
            :bordered="false"
            :class="{ 'card-selected': selectedItems.has(item.item_id) }"
            @click="handleCardClick($event, item, index)"
          >
            <n-checkbox
              class="card-checkbox"
              :checked="selectedItems.has(item.item_id)"
            />
            
            <!-- ★★★ 核心结构：card-inner-layout 包裹层 ★★★ -->
            <div class="card-inner-layout">
              
              <!-- 左侧海报 -->
              <div class="card-poster-container" @click.stop="handleCardClick($event, item, index)">
                <n-image 
                  lazy 
                  :src="getPosterUrl(item)" 
                  class="card-poster" 
                  object-fit="cover"
                  preview-disabled
                >
                  <template #placeholder><div class="poster-placeholder"></div></template>
                </n-image>
                
                <!-- 印章 -->
                <div v-if="item.status === 'needed'" class="poster-stamp stamp-needed">需处理</div>
                <div v-else-if="item.status === 'ignored'" class="poster-stamp stamp-ignored">已忽略</div>
                <div v-else-if="item.status === 'subscribed'" class="poster-stamp stamp-subscribed">处理中</div>
              </div>

              <!-- 右侧内容 -->
              <div class="card-content-container">
                
                <div class="content-top">
                  <div class="card-header">
                    <n-ellipsis class="card-title" :tooltip="{ style: { maxWidth: '300px' } }">
                      {{ item.item_name }}
                    </n-ellipsis>
                  </div>
                  
                  <div class="card-status-area">
                    <n-space vertical size="small" :wrap="false">
                      <!-- 状态文本 -->
                      <div v-if="item.status === 'needed'" class="reason-text-wrapper text-needed">
                        <n-icon :component="AlertCircleOutline" />
                        <n-ellipsis :tooltip="true">{{ item.reason }}</n-ellipsis>
                      </div>
                      <div v-else-if="item.status === 'ignored'" class="reason-text-wrapper text-ignored">
                        <n-icon :component="AlertCircleOutline" />
                        <n-ellipsis :tooltip="true">(已忽略) {{ item.reason }}</n-ellipsis>
                      </div>
                      <div v-else-if="item.status === 'subscribed'" class="reason-text-wrapper text-subscribed">
                        <n-icon :component="SyncOutline" />
                        <n-ellipsis :tooltip="true">(处理中) {{ item.reason }}</n-ellipsis>
                      </div>
                      <n-tag v-else :type="getStatusInfo(item.status).type" size="small" round>
                        {{ getStatusInfo(item.status).text }}
                      </n-tag>

                      <!-- 媒体信息 (紧凑展示) -->
                      <div class="meta-info-grid">
                        <n-text :depth="3" class="info-text">分辨率: {{ item.resolution_display }}</n-text>
                        
                        <n-tooltip trigger="hover" placement="top-start" :disabled="!item.release_group_raw || item.release_group_raw.length === 0">
                            <template #trigger>
                              <n-text :depth="3" class="info-text">质量: {{ item.quality_display }}</n-text>
                            </template>
                            发布组: {{ item.release_group_raw ? item.release_group_raw.join(', ') : '' }}
                        </n-tooltip>

                        <n-text :depth="3" class="info-text">编码: {{ item.codec_display }}</n-text>
                        <n-text :depth="3" class="info-text">特效: {{ Array.isArray(item.effect_display) ? item.effect_display.join(', ') : item.effect_display }}</n-text>
                        
                        <n-tooltip trigger="hover" placement="top-start">
                            <template #trigger><n-text :depth="3" class="info-text ellipsis full-width-item">音轨: {{ item.audio_display }}</n-text></template>
                            {{ item.audio_display }}
                        </n-tooltip>
                        
                        <n-tooltip trigger="hover" placement="top-start">
                            <template #trigger><n-text :depth="3" class="info-text ellipsis full-width-item">字幕: {{ item.subtitle_display }}</n-text></template>
                            {{ item.subtitle_display }}
                        </n-tooltip>
                        <!-- 缺集展示 -->
                        <n-tooltip v-if="item.missing_episodes && item.missing_episodes.length > 0" trigger="hover" placement="top-start">
                            <template #trigger>
                                <n-text class="info-text full-width-item" style="color: var(--n-error-color);">
                                    <n-icon :component="AlertCircleOutline" style="vertical-align: -2px; margin-right: 2px;" />
                                    缺失: {{ item.missing_episodes.length }} 集
                                </n-text>
                            </template>
                            缺失集号: {{ item.missing_episodes.join(', ') }}
                        </n-tooltip>
                      </div>
                    </n-space>
                  </div>
                </div>

                <!-- 底部按钮 -->
                <div class="card-actions-bottom">
                  <n-space align="center" justify="start" size="small" wrap>
                      <n-button 
                        v-if="item.status === 'needed'" 
                        size="tiny" 
                        :type="getActionInfo(item).type" 
                        ghost 
                        @click.stop="resubscribeItem(item)" 
                        :loading="subscribing[item.item_id]"
                      >
                        {{ getActionInfo(item).text }}
                      </n-button>
                      <n-button v-if="item.status === 'needed'" size="tiny" @click.stop="ignoreItem(item)">忽略</n-button>
                      <n-button v-if="item.status === 'ignored'" size="tiny" @click.stop="unignoreItem(item)">恢复</n-button>
                      <n-button text @click.stop="openInEmby(item)"><n-icon :component="EmbyIcon" size="18" /></n-button>
                      <n-button text tag="a" :href="`https://www.themoviedb.org/${item.item_type === 'Movie' ? 'movie' : 'tv'}/${item.tmdb_id}`" target="_blank" @click.stop><n-icon :component="TMDbIcon" size="18" /></n-button>
                  </n-space>
                </div>

              </div>
            </div>
            <!-- 布局结束 -->

          </n-card>
        </div>
      </div>
      <!-- Grid 结束 -->

      <div ref="loaderTrigger" class="loader-trigger">
        <n-spin v-if="displayedItems.length < filteredItems.length" size="small" />
      </div>
    </div>
      <div v-else class="center-container"><n-empty description="缓存为空，或当前筛选条件下无项目。" size="huge" /></div>
    </div>

    <n-modal v-model:show="showSettingsModal" preset="card" class="modal-card-lite" style="width: 90%; max-width: 800px;" title="规则设定">
      <ResubscribeSettingsPage @saved="handleSettingsSaved" />
    </n-modal>
  </div>
</template>

<script setup>
import { ref, onMounted, onUnmounted, computed, h, watch, nextTick } from 'vue';
import axios from 'axios';
import { NPageHeader, NDivider, NEmpty, NTag, NButton, NSpace, NIcon, useMessage, NGrid, NGi, NCard, NImage, NEllipsis, NSpin, NAlert, NRadioGroup, NRadioButton, NModal, NTooltip, NText, NDropdown, useDialog, NCheckbox, NInput, NSelect, NButtonGroup } from 'naive-ui';
import { SyncOutline, ArrowUpOutline as ArrowUpIcon, ArrowDownOutline as ArrowDownIcon, AlertCircleOutline } from '@vicons/ionicons5';
import { useConfig } from '../composables/useConfig.js';
import ResubscribeSettingsPage from './settings/ResubscribeSettingsPage.vue';

const EmbyIcon = () => h('svg', { xmlns: "http://www.w3.org/2000/svg", viewBox: "0 0 48 48", width: "18", height: "18" }, [ h('path', { d: "M24,4.2c-11,0-19.8,8.9-19.8,19.8S13,43.8,24,43.8s19.8-8.9,19.8-19.8S35,4.2,24,4.2z M24,39.8c-8.7,0-15.8-7.1-15.8-15.8S15.3,8.2,24,8.2s15.8,7.1,15.8,15.8S32.7,39.8,24,39.8z", fill: "currentColor" }), h('polygon', { points: "22.2,16.4 22.2,22.2 16.4,22.2 16.4,25.8 22.2,25.8 22.2,31.6 25.8,31.6 25.8,25.8 31.6,31.6 31.6,22.2 25.8,22.2 25.8,16.4 ", fill: "currentColor" })]);
const TMDbIcon = () => h('svg', { xmlns: "http://www.w3.org/2000/svg", viewBox: "0 0 512 512", width: "18", height: "18" }, [ h('path', { d: "M256 512A256 256 0 1 0 256 0a256 256 0 1 0 0 512zM133.2 176.6a22.4 22.4 0 1 1 0-44.8 22.4 22.4 0 1 1 0 44.8zm63.3-22.4a22.4 22.4 0 1 1 44.8 0 22.4 22.4 0 1 1 -44.8 0zm74.8 108.2c-27.5-3.3-50.2-26-53.5-53.5a8 8 0 0 1 16-.6c2.3 19.3 18.8 34 38.1 31.7a8 8 0 0 1 7.4 8c-2.3.3-4.5.4-6.8.4zm-74.8-108.2a22.4 22.4 0 1 1 44.8 0 22.4 22.4 0 1 1 -44.8 0zm149.7 22.4a22.4 22.4 0 1 1 0-44.8 22.4 22.4 0 1 1 0 44.8zM133.2 262.6a22.4 22.4 0 1 1 0-44.8 22.4 22.4 0 1 1 0 44.8zm63.3-22.4a22.4 22.4 0 1 1 44.8 0 22.4 22.4 0 1 1 -44.8 0zm74.8 108.2c-27.5-3.3-50.2-26-53.5-53.5a8 8 0 0 1 16-.6c2.3 19.3 18.8 34 38.1 31.7a8 8 0 0 1 7.4 8c-2.3.3-4.5.4-6.8.4zm-74.8-108.2a22.4 22.4 0 1 1 44.8 0 22.4 22.4 0 1 1 -44.8 0zm149.7 22.4a22.4 22.4 0 1 1 0-44.8 22.4 22.4 0 1 1 0 44.8z", fill: "#01b4e4" })]);

const { configModel } = useConfig();
const message = useMessage();
const dialog = useDialog();
const props = defineProps({ taskStatus: { type: Object, required: true } });

const allItems = ref([]); 
const displayedItems = ref([]); 
const filter = ref('all');
const isLoading = ref(true);
const error = ref(null);
const showSettingsModal = ref(false);
const subscribing = ref({});
const loaderTrigger = ref(null); 
const PAGE_SIZE = 24; 

const selectedItems = ref(new Set());
const lastSelectedIndex = ref(-1);

const searchQuery = ref('');
const sortBy = ref('item_name');
const sortOrder = ref('asc');
const mediaTypeFilter = ref(null); 
const mediaTypeOptions = ref([ 
  { label: '全部类型', value: null },
  { label: '电影', value: 'Movie' },
  { label: '剧集', value: 'Series' },
]);
const ruleFilter = ref(null); 
const ruleOptions = ref([{ label: '全部规则', value: null }]); 

const sortOptions = ref([
  { label: '按名称', value: 'item_name' },
]);

const isTaskRunning = (taskName) => props.taskStatus.is_running && props.taskStatus.current_action.includes(taskName);

const filteredItems = computed(() => {
  let items = [...allItems.value];

  if (filter.value === 'needed') {
    items = items.filter(item => item.status === 'needed');
  } else if (filter.value === 'ignored') {
    items = items.filter(item => item.status === 'ignored');
  } else if (filter.value === 'subscribed') {
    items = items.filter(item => item.status === 'subscribed');
  }

  if (searchQuery.value) {
    const query = searchQuery.value.toLowerCase();
    items = items.filter(item => item.item_name.toLowerCase().includes(query));
  }

  if (mediaTypeFilter.value) {
    items = items.filter(item => item.conceptual_type === mediaTypeFilter.value);
  }

  if (ruleFilter.value !== null) {
    items = items.filter(item => item.matched_rule_id === ruleFilter.value);
  }

  items.sort((a, b) => {
    const valA = a[sortBy.value];
    const valB = b[sortBy.value];
    
    let comparison = 0;
    if (typeof valA === 'string' && typeof valB === 'string') {
      comparison = valA.localeCompare(valB, 'zh-Hans-CN');
    } else {
      comparison = valA > valB ? 1 : (valA < valB ? -1 : 0);
    }
    
    return sortOrder.value === 'desc' ? -comparison : comparison;
  });

  return items;
});

const getStatusInfo = (status) => {
  switch (status) {
    case 'needed': return { text: '需处理', type: 'warning' };
    case 'subscribed': return { text: '处理中', type: 'info' };
    case 'ignored': return { text: '已忽略', type: 'tertiary' };
    case 'ok': default: return { text: '已达标', type: 'success' };
  }
};

const fetchData = async () => {
  isLoading.value = true;
  error.value = null;
  selectedItems.value.clear(); 
  lastSelectedIndex.value = -1;
  try {
    const response = await axios.get('/api/resubscribe/library_status');
    allItems.value = response.data;
  } catch (err)
 {
    error.value = err.response?.data?.error || '获取状态失败。';
  } finally {
    isLoading.value = false;
  }
};

const loadMore = () => {
  if (isLoading.value || displayedItems.value.length >= filteredItems.value.length) return;
  const currentLength = displayedItems.value.length;
  const nextItems = filteredItems.value.slice(currentLength, currentLength + PAGE_SIZE);
  displayedItems.value.push(...nextItems);
};

let observer = null;
const setupObserver = () => {
  if (observer) observer.disconnect();
  nextTick(() => {
    if (loaderTrigger.value) {
      observer = new IntersectionObserver((entries) => {
        if (entries[0].isIntersecting) loadMore();
      }, { rootMargin: '200px' });
      observer.observe(loaderTrigger.value);
    }
  });
};

watch(filteredItems, (newFilteredItems) => {
  displayedItems.value = newFilteredItems.slice(0, PAGE_SIZE);
  selectedItems.value.clear();
  lastSelectedIndex.value = -1;
  setupObserver();
}, { immediate: true });

onMounted(async () => {
  isLoading.value = true;
  try {
    await Promise.all([
      fetchData(),
      fetchRules()
    ]);
  } catch (e) {
    console.error("初始化数据加载失败", e);
  } finally {
    isLoading.value = false;
  }
});
onUnmounted(() => { if (observer) observer.disconnect(); });

const fetchRules = async () => {
  try {
    const response = await axios.get('/api/resubscribe/rules');
    ruleOptions.value = [{ label: '全部规则', value: null }, ...response.data.map(rule => ({
      label: rule.name,
      value: rule.id
    }))];
  } catch (err) {
    message.error('获取规则列表失败。');
  }
};

const handleCardClick = (event, item, index) => {
  const itemId = item.item_id;
  const isSelected = selectedItems.value.has(itemId);

  const displayedIndex = displayedItems.value.findIndex(d => d.item_id === itemId);

  if (event.shiftKey && lastSelectedIndex.value !== -1) {
    const start = Math.min(lastSelectedIndex.value, displayedIndex);
    const end = Math.max(lastSelectedIndex.value, displayedIndex);
    for (let i = start; i <= end; i++) {
      const idInRange = displayedItems.value[i].item_id;
      selectedItems.value.add(idInRange);
    }
  } else {
    if (isSelected) {
      selectedItems.value.delete(itemId);
    } else {
      selectedItems.value.add(itemId);
    }
  }
  lastSelectedIndex.value = displayedIndex;
};

const batchActions = computed(() => {
  const actions = [];
  const noSelection = selectedItems.value.size === 0;

  if (filter.value === 'ignored') {
    actions.push({ label: '批量取消忽略', key: 'unignore', disabled: noSelection });
  } else {
    actions.push({ label: '批量整理', key: 'subscribe', disabled: noSelection });
    actions.push({ label: '批量忽略', key: 'ignore', disabled: noSelection });
  }
  actions.push({ type: 'divider', key: 'd1' });

  if (filter.value === 'needed') {
    actions.push({ label: '一键忽略当前页所有“需处理”项', key: 'oneclick-ignore' });
  }
  if (filter.value === 'ignored') {
    actions.push({ label: '一键取消忽略当前页所有项', key: 'oneclick-unignore' });
  }
  
  return actions;
});

const handleBatchAction = (key) => {
  let ids = [];
  let actionKey = key;
  let isOneClick = false;

  if (key.startsWith('oneclick-')) {
    isOneClick = true;
    actionKey = key.split('-')[1]; 
    
    ids = filteredItems.value.map(item => item.item_id);
    
    if (ids.length === 0) {
        message.warning("当前筛选条件下没有可操作的项目。");
        return;
    }
    
    dialog.warning({
        title: '批量操作确认',
        content: `确定要对当前视图下的 ${ids.length} 个项目执行“${actionKey === 'ignore' ? '忽略' : '取消忽略'}”操作吗？`,
        positiveText: '确定',
        negativeText: '取消',
        onPositiveClick: () => {
            executeBatchAction(actionKey, ids, isOneClick);
        }
    });
    return; 
  } else {
    ids = Array.from(selectedItems.value);
  }
  
  if (ids.length === 0) return;
  executeBatchAction(actionKey, ids, isOneClick);
};

const sendBatchActionRequest = async (actionKey, ids, isOneClick) => {
  const actionMap = { subscribe: 'subscribe', ignore: 'ignore', unignore: 'ok' };
  const action = actionMap[actionKey];

  try {
    const response = await axios.post('/api/resubscribe/batch_action', {
      item_ids: ids, action: action, is_one_click: isOneClick, filter: filter.value
    });
    message.success(response.data.message);
    
    if (!isOneClick) {
      const optimisticStatusMap = { subscribe: 'subscribed', ignore: 'ignored', unignore: 'ok' };
      const optimisticStatus = optimisticStatusMap[actionKey];
      if (optimisticStatus === 'ok') {
        allItems.value = allItems.value.filter(i => !ids.includes(i.item_id));
      } else {
        ids.forEach(id => {
          const item = allItems.value.find(i => i.item_id === id);
          if (item) item.status = optimisticStatus;
        });
      }
      selectedItems.value.clear();
    } else {
      fetchData();
    }
  } catch (err) {
    message.error(err.response?.data?.error || `批量操作失败。`);
  }
};

const executeBatchAction = async (actionKey, ids, isOneClick) => {
  sendBatchActionRequest(actionKey, ids, isOneClick);
};

const ignoreItem = async (item) => {
  try {
    await axios.post('/api/resubscribe/batch_action', { item_ids: [item.item_id], action: 'ignore' });
    message.success(`《${item.item_name}》已忽略。`);
    const itemInList = allItems.value.find(i => i.item_id === item.item_id);
    if (itemInList) {
      itemInList.status = 'ignored';
    }
  } catch (err) {
    message.error(err.response?.data?.error || '忽略失败。');
  }
};

const unignoreItem = async (item) => {
  try {
    await axios.post('/api/resubscribe/batch_action', { item_ids: [item.item_id], action: 'ok' });
    message.success(`《${item.item_name}》已取消忽略。`);
    allItems.value = allItems.value.filter(i => i.item_id !== item.item_id);
  } catch (err) {
    message.error(err.response?.data?.error || '取消忽略失败。');
  }
};

const triggerRefreshStatus = async () => {
  try {
    await axios.post('/api/resubscribe/refresh_status');
    message.success('刷新任务已提交，请稍后查看任务状态。');
  } catch (err) {
    message.error(err.response?.data?.error || '提交刷新任务失败。');
  }
};
const triggerResubscribeAll = async () => { try { await axios.post('/api/resubscribe/resubscribe_all'); message.success('一键整理任务已提交，请稍后查看任务状态。'); } catch (err) { message.error(err.response?.data?.error || '提交一键整理任务失败。'); }};
const resubscribeItem = async (item) => {
  subscribing.value[item.item_id] = true;
  try {
    const response = await axios.post('/api/resubscribe/batch_action', {
      item_ids: [item.item_id],
      action: 'subscribe' 
    });
    
    message.success("整理任务已提交");

    const itemInList = allItems.value.find(i => i.item_id === item.item_id);
    if (itemInList) {
      itemInList.status = 'subscribed'; 
    }
  } catch (err) {
    message.error(err.response?.data?.error || '整理请求失败。');
  } finally {
    subscribing.value[item.item_id] = false;
  }
};
const getPosterUrl = (item) => {
  if (item.poster_path) {
    return `https://image.tmdb.org/t/p/w500${item.poster_path}`;
  }
  return ''; 
};
const openInEmby = (item) => {
  const embyServerUrl = configModel.value?.emby_server_url;
  const serverId = configModel.value?.emby_server_id;
  if (!embyServerUrl) {
    message.error('Emby服务器地址未配置，无法跳转。');
    return;
  }

  let targetEmbyId = null;
  if (item.item_type === 'Movie') {
    targetEmbyId = item.emby_item_id;
  } else if (item.item_type === 'Season') {
    targetEmbyId = item.series_emby_id;
  }

  if (!targetEmbyId) {
    message.error('无法确定此项目的有效Emby ID，无法跳转。');
    return;
  }

  const baseUrl = embyServerUrl.endsWith('/') ? embyServerUrl.slice(0, -1) : embyServerUrl;
  let finalUrl = `${baseUrl}/web/index.html#!/item?id=${targetEmbyId}`;
  if (serverId) {
    finalUrl += `&serverId=${serverId}`;
  }
  window.open(finalUrl, '_blank');
};
const getActionInfo = (item) => {
  if (item.action === 'delete') {
    return { text: '删除', type: 'error' };
  }
  return { text: '洗版', type: 'primary' };
};
const handleSettingsSaved = async (payload = {}) => {
  showSettingsModal.value = false; 
  if (payload.needsRefresh) {
    await fetchData(); 
    message.success('规则已更新，列表已刷新。');
  } else {
    message.success('规则已保存。如需应用新规则，请点击“扫描媒体库”按钮。');
  }
};

watch(() => props.taskStatus, (newStatus, oldStatus) => {
  if (oldStatus.is_running && !newStatus.is_running) {
    const relevantActions = [
      '刷新媒体整理', 
      '批量媒体整理',
      '批量删除媒体'   
    ];
    
    if (relevantActions.some(action => oldStatus.current_action.includes(action))) {
      message.info('相关后台任务已结束，正在刷新海报墙...');
      fetchData();
    }
  }
}, { deep: true }); 
</script>

<style scoped>
.page-container {
  /* 防止小屏幕下出现横向滚动条 */
  max-width: 100vw;
  overflow-x: hidden;
}
.center-container { display: flex; justify-content: center; align-items: center; height: calc(100vh - 200px); }

/* ★★★ 筛选栏响应式布局 ★★★ */
.filter-bar {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-top: 24px;
  margin-bottom: -12px;
  gap: 16px;
  flex-wrap: wrap;
}
.filter-input-search {
  width: 240px;
}
.filter-options {
  display: flex;
  align-items: center;
  gap: 12px;
  flex-wrap: wrap;
}
.filter-select-type { width: 120px; }
.filter-select-rule { width: 200px; }
.filter-select-sort { width: 150px; }

/* 移动端覆盖样式 */
@media (max-width: 768px) {
  .page-container {
    padding: 12px !important;
  }
  .header-actions {
    margin-top: 12px;
    justify-content: flex-start;
  }
  .status-radio-group {
    /* 如果按钮字太多，允许其折行 */
    flex-wrap: wrap;
  }
  .filter-bar {
    flex-direction: column;
    align-items: stretch;
  }
  .filter-input-search,
  .filter-select-type,
  .filter-select-rule,
  .filter-select-sort {
    width: 100% !important;
  }
  .filter-options {
    flex-direction: column;
    align-items: stretch;
  }
  .filter-sort-btns {
    display: flex;
  }
  .filter-sort-btns .n-button {
    flex: 1;
  }
}

/* ★★★ 响应式 Grid 布局 ★★★ */
.responsive-grid {
  display: grid;
  gap: 16px;
  /* 自动填充，最小宽度280px，完美适配手机和电脑 */
  grid-template-columns: repeat(auto-fill, minmax(280px, 1fr));
}

@media (max-width: 768px) {
  .responsive-grid {
    grid-template-columns: 1fr; /* 手机端强制单列 */
    gap: 12px;
  }
}

.grid-item { height: 100%; min-width: 0; }

/* ★★★ 毛玻璃卡片容器 ★★★ */
.series-card {
  cursor: pointer;
  transition: transform 0.2s ease-in-out, box-shadow 0.2s ease-in-out;
  height: 100%;
  position: relative;
  border-radius: 12px;
  overflow: hidden; 
  /* 继承全局毛玻璃属性 */
  background: rgba(20, 25, 35, 0.4) !important;
  backdrop-filter: blur(16px) !important;
  -webkit-backdrop-filter: blur(16px) !important;
  border: 1px solid rgba(255, 255, 255, 0.1) !important;
}

.series-card:hover {
  transform: translateY(-4px);
  box-shadow: 0 12px 32px rgba(0,0,0,0.4) !important;
  background: rgba(30, 35, 45, 0.5) !important;
  border-color: rgba(255, 255, 255, 0.2) !important;
}

.series-card :deep(.n-card__content) {
  padding: 12px !important; 
  display: flex !important;
  flex-direction: column !important;
  height: 100% !important;
}

/* 内部布局：左右拉伸 */
.card-inner-layout {
  display: flex;
  flex-direction: row;
  height: 100%;
  width: 100%;
  align-items: stretch; 
  gap: 16px;
}

/* 海报区域 */
.card-poster-container {
  flex-shrink: 0; 
  width: 110px;
  height: auto; 
  min-height: 100%; 
  position: relative;
  background-color: rgba(0,0,0,0.2);
  border-radius: 8px;
  overflow: hidden;
  box-shadow: 0 4px 12px rgba(0,0,0,0.3);
}

@media (max-width: 768px) {
  .card-poster-container {
    width: 90px; /* 移动端微调海报宽度，给文字留更多空间 */
  }
}

.card-poster { width: 100%; height: 100%; display: block; }
.card-poster :deep(img) { width: 100%; height: 100%; object-fit: cover !important; display: block; }

.poster-placeholder {
  display: flex; align-items: center; justify-content: center;
  width: 100%; height: 100%; background-color: rgba(255,255,255,0.05); color: rgba(255,255,255,0.3);
}

/* 内容区域 */
.card-content-container {
  flex-grow: 1; display: flex; flex-direction: column; justify-content: space-between; min-width: 0; padding: 0;
}

.card-header {
  display: flex; justify-content: space-between; align-items: flex-start; gap: 8px; margin-bottom: 8px;
}

.card-title {
  font-weight: 600; font-size: 1.1rem; line-height: 1.3; color: #fff;
  display: -webkit-box; -webkit-line-clamp: 2; line-clamp: 2; -webkit-box-orient: vertical; overflow: hidden;
}

.card-status-area { flex-grow: 1; display: flex; flex-direction: column; gap: 6px; }
.info-text, .info-line { font-size: 13px; color: rgba(255,255,255,0.6); display: flex; align-items: center; gap: 6px; }

/* 底部按钮区域 */
.card-actions {
  margin-top: auto; padding-top: 12px; border-top: 1px solid rgba(255,255,255,0.05);
  display: flex; justify-content: flex-start; align-items: center; gap: 8px;
}
</style>