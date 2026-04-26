<!-- src/components/UserCenterPage.vue -->
<template>
  <div class="modular-page-container"> 
    
    <!-- 头部问候语模块 -->
    <div class="page-header-module">
      <h1 class="greeting-title">早安，👋 <br class="mobile-break"/>欢迎回来, {{ accountInfo?.name || authStore.username }}</h1>
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

    <!-- 2. 中部模块：账户信息 & 播放记录 (电脑端并列显示) -->
    <n-grid :x-gap="24" :y-gap="24" cols="1 m:2" responsive="screen" style="margin-bottom: 24px;">
      
      <!-- 左侧/上方：账户信息卡片 -->
      <n-gi>
        <n-card :bordered="false" class="dashboard-card action-module" style="height: 100%;">
          <template #header><span class="card-title">账户详情</span></template>
          
          <!-- 用户信息与等级信息同行显示 -->
          <div class="account-info-horizontal">
            <!-- 头像与昵称 -->
            <div class="profile-header">
              <div class="avatar-wrapper" @click="triggerFileUpload">
                <n-avatar :size="64" :src="avatarUrl" object-fit="cover" style="background-color: rgba(255,255,255,0.1);">
                  <span v-if="!avatarUrl">{{ authStore.username ? authStore.username.charAt(0).toUpperCase() : 'U' }}</span>
                </n-avatar>
                <input type="file" ref="fileInput" style="display: none" accept="image/*" @change="handleAvatarChange" />
              </div>
              <div class="profile-text">
                <div class="profile-name">{{ accountInfo?.name || authStore.username }}</div>
                <n-tag :type="statusType" size="small" round :bordered="false">{{ statusText }}</n-tag>
              </div>
            </div>
            
            <!-- 等级与权限信息 (背景透明，分散居中) -->
            <div class="info-grid">
              <div class="info-row">
                <span class="info-label">账户等级</span>
                <span class="info-value">{{ authStore.isAdmin ? '管理员' : (accountInfo?.template_name || '未分配') }}</span>
              </div>
              <div class="info-row">
                <span class="info-label">到期时间</span>
                <span class="info-value">{{ accountInfo?.expiration_date ? new Date(accountInfo.expiration_date).toLocaleDateString() : '永久有效' }}</span>
              </div>
              <div class="info-row">
                <span class="info-label">订阅权限</span>
                <span class="info-value">{{ authStore.isAdmin || accountInfo?.allow_unrestricted_subscriptions ? '免审核' : '需审核' }}</span>
              </div>
            </div>
          </div>

          <n-divider style="margin: 16px 0; opacity: 0.2;" />
          
          <!-- Telegram 绑定区域 -->
          <div class="action-form">
            <span style="font-size: 12px; color: rgba(255,255,255,0.6); margin-bottom: 8px; display: block;">Telegram 通知 ID</span>
            <n-input-group>
              <n-input v-model:value="telegramChatId" placeholder="输入 Chat ID" size="small" style="background: rgba(255,255,255,0.05);" />
              <n-button type="primary" ghost :loading="isSavingChatId" @click="saveChatId" size="small">保存</n-button>
            </n-input-group>
            <n-button block ghost type="primary" style="margin-top: 12px; background: rgba(255,255,255,0.05);" @click="openBotChat">
              绑定 Telegram 机器人
            </n-button>
          </div>
        </n-card>
      </n-gi>

      <!-- 右侧/下方：播放记录卡片 -->
      <n-gi>
        <n-card :bordered="false" class="dashboard-card action-module" style="height: 100%;">
          <template #header><span class="card-title">近期播放</span></template>
          <!-- 播放数据 (去除了黑色背景，改为透明) -->
          <n-grid :cols="2" style="margin-bottom: 16px; text-align: center; padding: 12px 0;">
            <n-gi>
              <div style="font-size: 28px; font-weight: bold; color: #fff;">{{ playbackData?.personal?.total_count || 0 }}</div>
              <div style="font-size: 13px; color: rgba(255,255,255,0.5); margin-top: 4px;">观看次数</div>
            </n-gi>
            <n-gi>
              <div style="font-size: 28px; font-weight: bold; color: #fff;">{{ (playbackData?.personal?.total_minutes / 60).toFixed(1) }}</div>
              <div style="font-size: 13px; color: rgba(255,255,255,0.5); margin-top: 4px;">累计小时</div>
            </n-gi>
          </n-grid>
          <n-empty v-if="!playbackData?.personal?.history_list?.length" description="暂无播放记录" style="margin-top: 30px;" />
        </n-card>
      </n-gi>
    </n-grid>

    <!-- 3. 底部模块：订阅历史列表 (独占一行) -->
    <n-card :bordered="false" class="dashboard-card list-module">
      <template #header>
        <span class="card-title">最近的订阅动态</span>
      </template>
      <template #header-extra>
        <n-radio-group v-model:value="filterStatus" size="small" class="custom-radio-group">
          <n-radio-button value="all">全部</n-radio-button>
          <n-radio-button value="completed">已完成</n-radio-button>
          <n-radio-button value="processing">处理中</n-radio-button>
        </n-radio-group>
      </template>
      
      <n-spin :show="loading">
        <div v-if="subscriptionHistory.length > 0" class="custom-list">
          <div v-for="item in subscriptionHistory" :key="item.id" class="custom-list-item">
            <!-- 左侧图标块 -->
            <div class="item-icon-block" :class="getStatusType(item.status)">
              {{ item.item_type === 'Movie' ? '电影' : '剧集' }}
            </div>
            <!-- 中间内容 -->
            <div class="item-content">
              <div class="item-title">{{ item.title }}</div>
              <div class="item-desc">
                <n-tag :type="getStatusType(item.status)" size="tiny" :bordered="false" round style="margin-right: 8px;">
                  {{ getStatusText(item.status) }}
                </n-tag>
                <span v-if="item.notes">备注: {{ item.notes }}</span>
              </div>
            </div>
            <!-- 右侧时间 -->
            <div class="item-meta">
              <div class="item-time">{{ new Date(item.requested_at).toLocaleDateString() }}</div>
            </div>
          </div>
        </div>
        <n-empty v-else description="暂无订阅记录" style="margin: 40px 0;" />
      </n-spin>

      <div v-if="totalRecords > pageSize" style="margin-top: 20px; display: flex; justify-content: center;">
        <n-pagination v-model:page="currentPage" :page-size="pageSize" :item-count="totalRecords" simple @update:page="fetchSubscriptionHistory" class="custom-pagination" />
      </div>
    </n-card>

  </div>
</template>

<script setup>
import { ref, onMounted, onUnmounted, computed, h, watch } from 'vue';
import axios from 'axios';
import { useAuthStore } from '../stores/auth';
import { 
  NPageHeader, NCard, NDescriptions, NDescriptionsItem, NTag, NEmpty, NGrid, NGi, 
  NDataTable, NInputGroup, NInput, NButton, NText, useMessage, NPagination, 
  NStatistic, NRadioGroup, NRadioButton, NAvatar, NIcon, NDivider, NTooltip, NSpin,
  NTabs, NTabPane, NList, NListItem, NThing, NSpace, NAlert
} from 'naive-ui';

const authStore = useAuthStore();
const loading = ref(true);
const accountInfo = ref(null);
const subscriptionHistory = ref([]);
const telegramChatId = ref('');
const isSavingChatId = ref(false);
const message = useMessage();
const isFetchingBotLink = ref(false);
const playbackData = ref(null);
const playbackFilter = ref('all');
const playbackLoading = ref(false);

const currentPage = ref(1);
const pageSize = ref(10); 
const totalRecords = ref(0);
const stats = ref({ total: 0, completed: 0, processing: 0, pending: 0, failed: 0 });
const filterStatus = ref('all');
const fileInput = ref(null);

const avatarUrl = computed(() => {
  const tag = accountInfo.value?.profile_image_tag;
  const userId = accountInfo.value?.id;
  if (userId && tag) {
    return `/image_proxy/Users/${userId}/Images/Primary?tag=${tag}`;
  }
  return null;
});

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

const saveChatId = async () => {
  isSavingChatId.value = true;
  try {
    const response = await axios.post('/api/portal/telegram-chat-id', { chat_id: telegramChatId.value });
    message.success(response.data.message || '保存成功！');
  } catch (error) {
    message.error(error.response?.data?.message || '保存失败');
  } finally {
    isSavingChatId.value = false;
  }
};

const openBotChat = async () => {
  isFetchingBotLink.value = true;
  try {
    const response = await axios.get('/api/portal/telegram-bot-info');
    const botName = response.data.bot_username;
    if (botName) {
      window.open(`https://t.me/${botName}`, '_blank');
    } else {
      message.error(response.data.error || '未能获取到机器人信息', { duration: 8000 });
    }
  } catch (error) {
    message.error('请求机器人信息失败');
  } finally {
    isFetchingBotLink.value = false;
  }
};

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

watch(filterStatus, () => { fetchSubscriptionHistory(1); });

onMounted(async () => {
  try {
    const [accountResponse] = await Promise.all([ axios.get('/api/portal/account-info') ]);
    accountInfo.value = accountResponse.data;
    if (accountInfo.value) telegramChatId.value = accountInfo.value.telegram_chat_id || '';
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
/* 模块化页面基础容器 */
.modular-page-container {
  padding: 24px;
  max-width: 1600px;
  margin: 0 auto;
}

/* 头部问候语 */
.page-header-module {
  margin-bottom: 24px;
}
.greeting-title {
  font-size: 28px;
  font-weight: 700;
  margin: 0 0 8px 0;
  color: #fff;
  line-height: 1.3;
}
.greeting-subtitle {
  font-size: 14px;
  color: rgba(255,255,255,0.6);
  margin: 0;
}
.mobile-break { display: none; }

/* 强制统计模块字体为白色 */
.stat-module :deep(.n-statistic__label) {
  color: rgba(255, 255, 255, 0.7) !important; 
}
.stat-module :deep(.n-statistic-value__content) {
  color: var(--n-value-text-color, #ffffff) !important; 
  font-size: 28px;
  font-weight: bold;
}

/* 账户信息同行显示布局 */
.account-info-horizontal {
  display: flex;
  align-items: center;
  gap: 24px;
}
.profile-header {
  display: flex;
  align-items: center;
  gap: 16px;
  flex-shrink: 0;
}
.avatar-wrapper {
  cursor: pointer;
  border-radius: 50%;
  transition: transform 0.2s;
}
.avatar-wrapper:hover { transform: scale(1.05); }
.profile-name {
  font-size: 18px;
  font-weight: bold;
  color: #fff;
  margin-bottom: 4px;
}

/* 账户等级信息网格 (去背景，分散居中) */
.info-grid {
  flex: 1;
  display: grid;
  grid-template-columns: repeat(3, 1fr); /* 内部三列平分 */
  gap: 16px;
  align-items: center; /* 垂直居中 */
}
.info-row {
  display: flex;
  flex-direction: column; 
  align-items: center; /* 水平居中，实现分散居中效果 */
  gap: 4px;
}
.info-label { color: rgba(255,255,255,0.5); font-size: 12px; }
.info-value { color: #fff; font-weight: 500; font-size: 14px; }


/* 自定义列表样式 */
.custom-list {
  display: flex;
  flex-direction: column;
  gap: 12px;
}
.custom-list-item {
  display: flex;
  align-items: center;
  padding: 16px;
  background: rgba(0, 0, 0, 0.2);
  border-radius: 12px;
  border: 1px solid rgba(255, 255, 255, 0.05);
  transition: background 0.2s;
}
.custom-list-item:hover {
  background: rgba(255, 255, 255, 0.05);
}
.item-icon-block {
  width: 48px;
  height: 48px;
  border-radius: 12px;
  display: flex;
  align-items: center;
  justify-content: center;
  font-weight: bold;
  font-size: 12px;
  margin-right: 16px;
  flex-shrink: 0;
}
/* 图标块颜色映射 */
.item-icon-block.success { background: rgba(99, 226, 183, 0.2); color: #63e2b7; }
.item-icon-block.warning { background: rgba(242, 201, 125, 0.2); color: #f2c97d; }
.item-icon-block.info { background: rgba(112, 192, 232, 0.2); color: #70c0e8; }
.item-icon-block.error { background: rgba(232, 128, 128, 0.2); color: #e88080; }
.item-icon-block.default { background: rgba(255, 255, 255, 0.1); color: #fff; }

.item-content {
  flex: 1;
  min-width: 0;
}
.item-title {
  font-size: 15px;
  font-weight: 600;
  color: #fff;
  margin-bottom: 4px;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}
.item-desc {
  font-size: 12px;
  color: rgba(255,255,255,0.5);
  display: flex;
  align-items: center;
}
.item-meta {
  text-align: right;
  flex-shrink: 0;
  margin-left: 16px;
}
.item-time {
  font-size: 12px;
  color: rgba(255,255,255,0.4);
}

/* 手机端适配 */
@media (max-width: 768px) {
  .modular-page-container { padding: 12px; }
  .greeting-title { font-size: 22px; }
  .mobile-break { display: block; }
  
  /* 手机端账户信息改为上下折行，并恢复左右对齐以节省空间 */
  .account-info-horizontal { flex-direction: column; align-items: flex-start; gap: 16px; }
  .info-grid { grid-template-columns: 1fr; width: 100%; box-sizing: border-box; gap: 12px; }
  .info-row { flex-direction: row; justify-content: space-between; align-items: center; }
  
  .custom-list-item { padding: 12px; }
  .item-icon-block { width: 40px; height: 40px; margin-right: 12px; }
}
</style>