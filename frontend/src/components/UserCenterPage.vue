<!-- src/components/UserCenterPage.vue -->
<template>
  <div class="modular-page-container"> 
    
    <!-- 头部问候语模块 -->
    <div class="page-header-module">
      <h1 class="greeting-title">👋 欢迎回来, {{ accountInfo?.name || authStore.username }}</h1>
      <p class="greeting-subtitle">我帮您整理了最重要的账户状态与下一步建议。</p>
    </div>
    
    <!-- 1. 顶部统计数据模块 (响应式网格) -->
    <n-grid :x-gap="16" :y-gap="16" cols="2 s:3 m:5" responsive="screen" style="margin-bottom: 24px;">
      <n-gi><n-card class="dashboard-card stat-module" :bordered="false"><n-statistic label="总申请" :value="stats.total" /></n-card></n-gi>
      <n-gi><n-card class="dashboard-card stat-module" :bordered="false"><n-statistic label="已完成" :value="stats.completed" style="--n-value-text-color: #63e2b7" /></n-card></n-gi>
      <n-gi><n-card class="dashboard-card stat-module" :bordered="false"><n-statistic label="处理中" :value="stats.processing" style="--n-value-text-color: #70c0e8" /></n-card></n-gi>
      <n-gi><n-card class="dashboard-card stat-module" :bordered="false"><n-statistic label="待审核" :value="stats.pending" style="--n-value-text-color: #f2c97d" /></n-card></n-gi>
      <n-gi><n-card class="dashboard-card stat-module" :bordered="false"><n-statistic label="未通过" :value="stats.failed" style="--n-value-text-color: #e88080" /></n-card></n-gi>
    </n-grid>

    <!-- 2. 主体模块：账户信息、播放记录、订阅历史 (电脑端三列并排) -->
    <n-grid :x-gap="24" :y-gap="24" cols="1 m:2 l:3" responsive="screen" style="margin-bottom: 24px; align-items: stretch;">
      
      <!-- 第一列：账户信息卡片 -->
      <n-gi>
        <n-card :bordered="false" class="dashboard-card action-module" style="height: 100%;">
          <template #header><span class="card-title">账户详情</span></template>
          
          <!-- 用户信息垂直居中显示 -->
          <div class="account-info-vertical">
            <div class="profile-header-vertical">
              <div class="avatar-wrapper" @click="triggerFileUpload">
                <n-avatar round :size="64" :src="avatarUrl" object-fit="cover" style="background-color: rgba(255,255,255,0.1); width: 100%; height: 100%;">
                  <span v-if="!avatarUrl">{{ authStore.username ? authStore.username.charAt(0).toUpperCase() : 'U' }}</span>
                </n-avatar>
                <!-- 悬浮遮罩 -->
                <div class="avatar-overlay">更换</div>
                <input type="file" ref="fileInput" style="display: none" accept="image/*" @change="handleAvatarChange" />
              </div>
              <div class="profile-name">{{ accountInfo?.name || authStore.username }}</div>
            </div>
            
            <!-- 等级与权限信息网格 -->
            <div class="info-grid">
              <div class="info-row">
                <span class="info-label">账户等级</span>
                <span class="info-value">{{ authStore.isAdmin ? '管理员' : (accountInfo?.template_name || '未分配') }}</span>
              </div>
              <div class="info-row">
                <span class="info-label">等级说明</span>
                <span class="info-value desc-text">
                  {{ authStore.isAdmin ? '拥有系统所有管理权限' : (accountInfo?.template_description || '暂无说明') }}
                </span>
              </div>
              <div class="info-row">
                <span class="info-label">注册时间</span>
                <span class="info-value">{{ accountInfo?.registration_date ? new Date(accountInfo.registration_date).toLocaleDateString() : '-' }}</span>
              </div>
              <div class="info-row">
                <span class="info-label">到期时间</span>
                <span class="info-value">{{ accountInfo?.expiration_date ? new Date(accountInfo.expiration_date).toLocaleDateString() : '永久有效' }}</span>
              </div>
              <div class="info-row">
                <span class="info-label">账号状态</span>
                <span class="info-value" :class="`text-${statusType}`">
                  {{ statusText }}
                </span>
              </div>
              <div class="info-row">
                <span class="info-label">订阅权限</span>
                <span class="info-value" :class="{'text-success': authStore.isAdmin || accountInfo?.allow_unrestricted_subscriptions, 'text-warning': !authStore.isAdmin && !accountInfo?.allow_unrestricted_subscriptions}">
                  {{ authStore.isAdmin || accountInfo?.allow_unrestricted_subscriptions ? '免审核订阅' : '需审核订阅' }}
                </span>
              </div>
            </div>
          </div>
          
          <!-- Telegram 绑定区域 (仅普通用户显示频道按钮) -->
          <template v-if="!authStore.isAdmin">
            <n-divider style="margin: 16px 0; opacity: 0.2;" />
            <div class="action-form">
              <span style="font-size: 12px; color: rgba(255,255,255,0.6); margin-bottom: 8px; display: block;">获取最新资讯与帮助</span>
              <n-button 
                v-if="globalChannelLink !== '#'"
                block ghost type="info" 
                @click="openTelegramChannel"
                style="background: rgba(255,255,255,0.05);"
              >
                点击加入频道 / 群组
              </n-button>
              <span v-else style="font-size: 12px; color: rgba(255,255,255,0.3);">管理员尚未配置频道链接</span>
            </div>
          </template>
        </n-card>
      </n-gi>

      <!-- 第二列：播放记录卡片 -->
      <n-gi>
        <n-card :bordered="false" class="dashboard-card action-module" style="height: 100%;">
          <template #header><span class="card-title">近期播放</span></template>
          <template #header-extra>
            <n-radio-group v-model:value="playbackFilter" size="small" @update:value="handleFilterChange">
              <n-radio-button value="all">全部</n-radio-button>
              <n-radio-button value="Movie">电影</n-radio-button>
              <n-radio-button value="Episode">剧集</n-radio-button>
              <n-radio-button value="Audio">音乐</n-radio-button>
            </n-radio-group>
          </template>

          <n-grid :cols="2" style="margin-bottom: 12px; text-align: center; padding-top: 8px;">
            <n-gi>
              <div style="font-size: 24px; font-weight: bold; color: #fff;">{{ playbackData?.personal?.total_count || 0 }}</div>
              <div style="font-size: 12px; color: rgba(255,255,255,0.5);">观看次数</div>
            </n-gi>
            <n-gi>
              <div style="font-size: 24px; font-weight: bold; color: #fff;">{{ (playbackData?.personal?.total_minutes / 60).toFixed(1) }}</div>
              <div style="font-size: 12px; color: rgba(255,255,255,0.5);">累计小时</div>
            </n-gi>
          </n-grid>

          <n-divider style="margin: 12px 0; opacity: 0.1;" />

          <n-scrollbar style="max-height: 240px;">
            <n-list hoverable clickable size="small" class="transparent-list">
              <n-list-item v-for="(item, index) in playbackData?.personal?.history_list" :key="index" style="padding: 8px;">
                <n-thing :title="item.title" content-style="margin-top: 0;">
                  <template #header>
                    <span style="font-size: 13px; color: #fff; font-weight: 500;">{{ item.title }}</span>
                  </template>
                  <template #description>
                    <div style="font-size: 11px; color: rgba(255,255,255,0.4);">
                      {{ new Date(item.date).toLocaleDateString() }} · {{ item.duration }} 分钟
                    </div>
                  </template>
                  <template #header-extra>
                    <n-tag :type="getTypeTagColor(item.item_type)" size="tiny" round :bordered="false">{{ ITEM_TYPE_MAP[item.item_type] || item.item_type }}</n-tag>
                  </template>
                </n-thing>
              </n-list-item>
            </n-list>
            <n-empty v-if="!playbackData?.personal?.history_list?.length" description="暂无播放记录" style="margin-top: 40px;" />
          </n-scrollbar>
        </n-card>
      </n-gi>

      <!-- 第三列：订阅历史卡片 -->
      <n-gi>
        <n-card :bordered="false" class="dashboard-card list-module" style="height: 100%;">
          <template #header>
            <span class="card-title">订阅历史</span>
          </template>
          <template #header-extra>
            <n-radio-group v-model:value="filterStatus" size="small" class="custom-radio-group">
              <n-radio-button value="all">全部</n-radio-button>
              <n-radio-button value="completed">已完成</n-radio-button>
              <n-radio-button value="processing">处理中</n-radio-button>
            </n-radio-group>
          </template>
          
          <n-spin :show="loading">
            <n-scrollbar style="max-height: 350px; padding-right: 8px;">
              <div v-if="subscriptionHistory.length > 0" class="custom-list">
                <div v-for="item in subscriptionHistory" :key="item.id" class="custom-list-item">
                  <div class="item-icon-block" :class="getStatusType(item.status)">
                    {{ item.item_type === 'Movie' ? '电影' : '剧集' }}
                  </div>
                  <div class="item-content">
                    <div class="item-title">{{ item.title }}</div>
                    <div class="item-desc">
                      <n-tag :type="getStatusType(item.status)" size="tiny" :bordered="false" round style="margin-right: 8px;">
                        {{ getStatusText(item.status) }}
                      </n-tag>
                      <span v-if="item.notes" style="background: rgba(255,255,255,0.05); padding: 2px 6px; border-radius: 4px; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; max-width: 100px;">
                        {{ item.notes }}
                      </span>
                    </div>
                  </div>
                  <div class="item-meta">
                    <div class="item-time">{{ new Date(item.requested_at).toLocaleDateString() }}</div>
                  </div>
                </div>
              </div>
              <n-empty v-else description="暂无订阅记录" style="margin: 40px 0;" />
            </n-scrollbar>
          </n-spin>

          <div v-if="totalRecords > pageSize" style="margin-top: 16px; display: flex; justify-content: center;">
            <n-pagination v-model:page="currentPage" :page-size="pageSize" :item-count="totalRecords" simple @update:page="fetchSubscriptionHistory" class="custom-pagination" />
          </div>
        </n-card>
      </n-gi>
    </n-grid>

  </div>
</template>

<script setup>
import { ref, onMounted, onUnmounted, computed, watch } from 'vue';
import axios from 'axios';
import { useAuthStore } from '../stores/auth';
import { 
  NCard, NTag, NEmpty, NGrid, NGi, NButton, 
  useMessage, NPagination, NStatistic, NRadioGroup, NRadioButton, 
  NAvatar, NDivider, NSpin, NList, NListItem, NThing, NScrollbar
} from 'naive-ui';

const authStore = useAuthStore();
const loading = ref(true);
const accountInfo = ref(null);
const subscriptionHistory = ref([]);
const message = useMessage();

const playbackData = ref(null);
const playbackFilter = ref('all');
const playbackLoading = ref(false);

const currentPage = ref(1);
const pageSize = ref(10); 
const totalRecords = ref(0);
const stats = ref({ total: 0, completed: 0, processing: 0, pending: 0, failed: 0 });
const filterStatus = ref('all');
const fileInput = ref(null);

const ITEM_TYPE_MAP = {
  Movie: '电影',
  Episode: '剧集',
  Audio: '音乐',
  Video: '视频'
};
const getTypeTagColor = (type) => {
    switch(type) {
        case 'Movie': return 'info';
        case 'Episode': return 'success';
        case 'Audio': return 'warning';
        case 'Video': return 'error';
        default: return 'default';
    }
};

const avatarUrl = computed(() => {
  const tag = accountInfo.value?.profile_image_tag;
  const userId = accountInfo.value?.id;
  if (userId && tag) {
    return `/image_proxy/Users/${userId}/Images/Primary?tag=${tag}`;
  }
  return null;
});

// 智能解析 Telegram 链接
const globalChannelLink = computed(() => {
  if (!accountInfo.value || !accountInfo.value.telegram_channel_id) return '#';
  const channelId = accountInfo.value.telegram_channel_id.trim();

  // 拦截：如果是 -100 开头的纯数字（Telegram 内部 ID），标记为特殊状态
  if (channelId.startsWith('-100') || /^-?\d+$/.test(channelId)) {
    return 'INTERNAL_ID';
  }

  // 正常处理公开链接或用户名
  if (channelId.startsWith('https://t.me/')) return channelId;
  if (channelId.startsWith('@')) return `https://t.me/${channelId.substring(1)}`;
  return `https://t.me/${channelId}`;
});

// 手动处理按钮点击跳转，防止内部 ID 错误跳转
const openTelegramChannel = () => {
  const link = globalChannelLink.value;
  
  if (link === 'INTERNAL_ID') {
    message.warning(
      '无法跳转：管理员配置了内部群组 ID (-100开头)。请管理员在后台将其修改为公开频道名 (如 @name) 或邀请链接。', 
      { duration: 6000 }
    );
    return;
  }
  
  if (link && link !== '#') {
    window.open(link, '_blank');
  } else {
    message.warning('管理员尚未配置有效的频道链接');
  }
};

const triggerFileUpload = () => { fileInput.value?.click(); };

const handleAvatarChange = async (event) => {
  const file = event.target.files[0];
  if (!file) return;
  if (!['image/jpeg', 'image/png', 'image/jpg'].includes(file.type)) {
    message.error('只支持 JPG/PNG 格式的图片');
    return;
  }
  const formData = new FormData();
  formData.append('avatar', file);
  const loadingMsg = message.loading('正在上传头像...', { duration: 0 });
  try {
    const res = await axios.post('/api/portal/upload-avatar', formData, {
      headers: { 'Content-Type': 'multipart/form-data' }
    });
    loadingMsg.destroy();
    message.success('头像更新成功！');
    if (accountInfo.value && res.data.new_tag) {
      accountInfo.value.profile_image_tag = res.data.new_tag;
    }
  } catch (error) {
    loadingMsg.destroy();
    message.error(error.response?.data?.message || '上传失败');
  } finally {
    event.target.value = ''; 
  }
};

const statusMap = {
  active: { text: '正常', type: 'success' },
  pending: { text: '待审批', type: 'warning' },
  expired: { text: '已过期', type: 'error' },
  disabled: { text: '已禁用', type: 'error' },
};

const statusText = computed(() => statusMap[accountInfo.value?.status]?.text || '未知');
const statusType = computed(() => statusMap[accountInfo.value?.status]?.type || 'default');

const getStatusInfo = (status) => {
  const map = {
    completed: { type: 'success', text: '已完成' },
    WANTED: { type: 'info', text: '处理中' }, 
    REQUESTED: { type: 'warning', text: '待审核' },
    IGNORED: { type: 'error', text: '已忽略' },
    SUBSCRIBED: { type: 'info', text: '已订阅' }, 
    PENDING_RELEASE: { type: 'error', text: '未上映' },
    NONE: { type: 'warning', text: '已取消' },
    PAUSED: { type: 'warning', text: '已暂停' },
  };
  return map[status] || { type: 'default', text: status };
};

const getStatusType = (status) => getStatusInfo(status).type;
const getStatusText = (status) => getStatusInfo(status).text;

const fetchStats = async () => {
  try {
    const res = await axios.get('/api/portal/subscription-stats');
    stats.value = res.data;
  } catch (e) { console.error("获取统计失败", e); }
};

const fetchSubscriptionHistory = async (page = 1) => {
  loading.value = true;
  try {
    const response = await axios.get('/api/portal/subscription-history', {
      params: { page: page, page_size: pageSize.value, status: filterStatus.value },
    });
    subscriptionHistory.value = response.data.items;
    totalRecords.value = response.data.total_records;
    currentPage.value = page;
  } catch (error) {
    message.error('加载订阅历史失败');
  } finally {
    loading.value = false;
  }
};

const fetchPlaybackStats = async () => {
  playbackLoading.value = true;
  try {
    const res = await axios.get(`/api/portal/playback-report?days=30&media_type=${playbackFilter.value}`);
    playbackData.value = res.data;
  } catch (error) {
    message.error("获取播放统计失败");
  } finally {
    playbackLoading.value = false;
  }
};

const handleFilterChange = () => { fetchPlaybackStats(); };

watch(filterStatus, () => { fetchSubscriptionHistory(1); });

onMounted(async () => {
  try {
    const [accountResponse] = await Promise.all([ axios.get('/api/portal/account-info') ]);
    accountInfo.value = accountResponse.data;
    fetchStats();
    await fetchSubscriptionHistory();
  } catch (error) {
    message.error('加载账户信息失败');
  } finally {
    loading.value = false;
  }
  fetchPlaybackStats();
});
</script>

<style scoped>
:deep(.n-card__content) { padding-top: 16px !important; }

.modular-page-container { padding: 24px; max-width: 1600px; margin: 0 auto; }

.page-header-module { margin-bottom: 24px; }
.greeting-title { font-size: 28px; font-weight: 700; margin: 0 0 8px 0; color: #fff; line-height: 1.3; }
.greeting-subtitle { font-size: 14px; color: rgba(255,255,255,0.6); margin: 0; }

.stat-module :deep(.n-statistic__label) { color: rgba(255, 255, 255, 0.7) !important; }
.stat-module :deep(.n-statistic-value__content) { color: var(--n-value-text-color, #ffffff) !important; font-size: 28px; font-weight: bold; }

/* 垂直排布样式 */
.account-info-vertical { display: flex; flex-direction: column; align-items: center; gap: 24px; }

/* 头像和名字垂直居中显示 */
.profile-header-vertical { display: flex; flex-direction: column; align-items: center; justify-content: center; gap: 12px; margin-top: 10px; width: 100%; }
.profile-name { font-size: 20px; font-weight: bold; color: #fff; margin: 0; text-align: center; }

.avatar-wrapper { 
  width: 64px; 
  height: 64px; 
  position: relative; 
  cursor: pointer; 
  border-radius: 50%; 
  overflow: hidden; 
  transition: transform 0.2s; 
  flex-shrink: 0; 
}
.avatar-wrapper:hover { transform: scale(1.05); }
.avatar-overlay {
  position: absolute; top: 0; left: 0; width: 100%; height: 100%;
  background-color: rgba(0, 0, 0, 0.5);
  display: flex; justify-content: center; align-items: center;
  opacity: 0; transition: opacity 0.2s;
  color: #fff; font-size: 12px; font-weight: bold; border-radius: 50%;
}
.avatar-wrapper:hover .avatar-overlay { opacity: 1; }

/* 信息网格：三行两列居中排列 */
.info-grid { 
  width: 100%; box-sizing: border-box; display: grid; grid-template-columns: repeat(2, 1fr); gap: 16px; 
  align-items: center; background: rgba(255,255,255,0.02); padding: 16px; border-radius: 8px;
}
.info-row { display: flex; flex-direction: column; align-items: center; text-align: center; gap: 6px; }
.info-label { color: rgba(255,255,255,0.5); font-size: 12px; }
.info-value { color: #fff; font-weight: 500; font-size: 13px; }
.desc-text { color: rgba(255,255,255,0.7); font-size: 12px; line-height: 1.4; }

/* 文字颜色类 */
.text-success { color: #63e2b7 !important; }
.text-warning { color: #f2c97d !important; }
.text-error { color: #e88080 !important; }
.text-default { color: #ffffff !important; }

.transparent-list { background: transparent !important; }
.transparent-list :deep(.n-list-item) { transition: background 0.2s; border-radius: 8px; }
.transparent-list :deep(.n-list-item:hover) { background: rgba(255,255,255,0.05); }

.custom-list { display: flex; flex-direction: column; gap: 12px; }
.custom-list-item {
  display: flex; align-items: center; padding: 12px 16px;
  background: rgba(0, 0, 0, 0.2); border-radius: 12px;
  border: 1px solid rgba(255, 255, 255, 0.05); transition: background 0.2s;
}
.custom-list-item:hover { background: rgba(255, 255, 255, 0.05); }
.item-icon-block {
  width: 44px; height: 44px; border-radius: 12px; display: flex;
  align-items: center; justify-content: center; font-weight: bold;
  font-size: 12px; margin-right: 12px; flex-shrink: 0;
}
.item-icon-block.success { background: rgba(99, 226, 183, 0.2); color: #63e2b7; }
.item-icon-block.warning { background: rgba(242, 201, 125, 0.2); color: #f2c97d; }
.item-icon-block.info { background: rgba(112, 192, 232, 0.2); color: #70c0e8; }
.item-icon-block.error { background: rgba(232, 128, 128, 0.2); color: #e88080; }
.item-icon-block.default { background: rgba(255, 255, 255, 0.1); color: #fff; }

.item-content { flex: 1; min-width: 0; }
.item-title { font-size: 14px; font-weight: 600; color: #fff; margin-bottom: 4px; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.item-desc { font-size: 12px; color: rgba(255,255,255,0.5); display: flex; align-items: center; }
.item-meta { text-align: right; flex-shrink: 0; margin-left: 12px; }
.item-time { font-size: 12px; color: rgba(255,255,255,0.4); }

@media (max-width: 768px) {
  .modular-page-container { padding: 12px; }
  .greeting-title { font-size: 22px; }
  .account-info-vertical { gap: 16px; }
  .profile-header-vertical { gap: 8px; }
  
  /* 移动端依然保持两列居中对齐 */
  .info-grid { grid-template-columns: repeat(2, 1fr); gap: 12px; }
  .info-row { flex-direction: column; justify-content: center; align-items: center; }
  .custom-list-item { padding: 12px; }
  .item-icon-block { width: 40px; height: 40px; margin-right: 12px; }
}
</style>