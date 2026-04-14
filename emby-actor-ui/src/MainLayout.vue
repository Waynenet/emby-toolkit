<!-- src/MainLayout.vue -->
<template>
  <n-layout has-sider class="app-main-layout">
    <!-- 移动端侧边栏遮罩 -->
    <div v-if="isMobile && !collapsed" class="mobile-sider-mask" @click="collapsed = true"></div>

    <!-- 侧边栏 (玻璃拟态) -->
    <n-layout-sider
      :bordered="false"
      collapse-mode="width"
      :collapsed-width="isMobile ? 0 : 64"
      :width="210"
      :show-trigger="isMobile ? false : 'bar'"
      :native-scrollbar="false"
      :collapsed="collapsed"
      @update:collapsed="val => collapsed = val"
      :class="['glass-sider', { 'mobile-sider': isMobile }]"
    >
      <div class="sider-content-wrapper">
        <!-- 顶部 Logo (纯图标/简约文字) -->
        <div class="sider-logo" :class="{ 'collapsed': collapsed && !isMobile }">
          <img :src="logo" alt="Logo" class="logo-img" />
        </div>

        <!-- 中间 导航菜单 -->
        <div class="sider-menu-container">
          <n-menu
            :collapsed="collapsed"
            :collapsed-width="64"
            :collapsed-icon-size="20"
            :options="menuOptions"
            :value="activeMenuKey"
            @update:value="handleMenuUpdate"
          />
        </div>

        <!-- 底部 工具栏与用户信息 -->
        <div class="sider-bottom-tools" v-show="!collapsed || isMobile">
          <n-divider style="margin: 0 0 16px 0; opacity: 0.5;" />
          
          <div class="tools-actions-row">
            <n-button-group v-if="authStore.isAdmin" size="small">
              <n-tooltip><template #trigger><n-button @click="isRealtimeLogVisible = true" circle ghost><template #icon><n-icon :component="ReaderOutline" /></template></n-button></template>实时日志</n-tooltip>
              <n-tooltip><template #trigger><n-button @click="isHistoryLogVisible = true" circle ghost><template #icon><n-icon :component="ArchiveOutline" /></template></n-button></template>历史日志</n-tooltip>
            </n-button-group>

            <!-- 明暗切换 -->
            <n-switch :value="props.isDark" @update:value="newValue => emit('update:is-dark', newValue)" size="small">
              <template #checked-icon><n-icon :component="MoonIcon" /></template>
              <template #unchecked-icon><n-icon :component="SunnyIcon" /></template>
            </n-switch>
          </div>

          <!-- 用户名下拉 -->
          <n-dropdown v-if="authStore.isLoggedIn" trigger="hover" :options="userOptions" @select="handleUserSelect">
            <div class="user-profile-btn">
              <n-icon size="20" :component="UserCenterIcon" />
              <span class="username-text">欢迎, {{ authStore.username }}</span>
            </div>
          </n-dropdown>

          <div class="app-version">v{{ appVersion }}</div>
        </div>
      </div>
    </n-layout-sider>

    <!-- 右侧内容区 -->
    <n-layout-content
      class="app-main-content"
      content-style="padding: 24px;"
      :native-scrollbar="false"
    >
      <!-- 移动端汉堡菜单悬浮按钮 -->
      <n-button v-if="isMobile" circle class="mobile-menu-btn" @click="collapsed = !collapsed">
        <template #icon><n-icon :component="MenuOutline" /></template>
      </n-button>

      <!-- 桌面端悬浮任务状态胶囊 -->
      <transition name="fade">
        <div 
          v-if="!isMobile && authStore.isAdmin && props.taskStatus && props.taskStatus.current_action !== '空闲' && props.taskStatus.current_action !== '无'"
          class="floating-task-pill"
        >
          <n-spin v-if="props.taskStatus.is_running" size="small" class="pill-icon" />
          <n-icon v-else :component="SchedulerIcon" class="pill-icon" style="opacity: 0.6;" />
          <div class="pill-text-area">
            <strong :style="{ color: props.taskStatus.is_running ? 'var(--accent-color)' : 'inherit' }">
              {{ props.taskStatus.current_action }}
            </strong>
            <span class="pill-divider">-</span>
            <span class="pill-msg">{{ props.taskStatus.message }}</span>
          </div>
          <n-button v-if="props.taskStatus.is_running" type="error" size="tiny" circle secondary @click="triggerStopTask" class="pill-stop-btn">
            <template #icon><n-icon :component="StopIcon" /></template>
          </n-button>
        </div>
      </transition>

      <div class="page-content-inner-wrapper">
        <router-view v-slot="slotProps">
          <component :is="slotProps.Component" :task-status="props.taskStatus" />
        </router-view>
      </div>
    </n-layout-content>
    
    <!-- 日志 Modal -->
    <n-modal v-model:show="isRealtimeLogVisible" preset="card" style="width: 95%; max-width: 900px;" title="实时任务日志" class="modal-card-lite">
       <n-log ref="logRef" :log="logContent" trim class="log-panel" style="height: 60vh; font-size: 13px; line-height: 1.6;"/>
    </n-modal>
    <LogViewer v-model:show="isHistoryLogVisible" />
  </n-layout>
</template>

<script setup>
import { ref, computed, h, watch, nextTick, onMounted, onUnmounted } from 'vue';
import { useRouter, useRoute } from 'vue-router';
import { NLayout, NLayoutSider, NLayoutContent, NMenu, NSwitch, NIcon, NModal, NDropdown, NButton, NTooltip, NProgress, NButtonGroup, NLog, useMessage, NDivider, NSpin } from 'naive-ui';
import { useAuthStore } from './stores/auth';
import LogViewer from './components/LogViewer.vue';
import { AnalyticsOutline as StatsIcon, ListOutline as ReviewListIcon, TimerOutline as SchedulerIcon, OptionsOutline as GeneralIcon, LogOutOutline as LogoutIcon, HeartOutline as WatchlistIcon, AlbumsOutline as CollectionsIcon, PeopleOutline as ActorSubIcon, CreateOutline as CustomCollectionsIcon, ColorPaletteOutline as PaletteIcon, Stop as StopIcon, SparklesOutline as ResubscribeIcon, TrashBinOutline as CleanupIcon, PeopleCircleOutline as UserManagementIcon, PersonCircleOutline as UserCenterIcon, FilmOutline as DiscoverIcon, ArchiveOutline as UnifiedSubIcon, PricetagOutline as TagIcon, CompassOutline, ReaderOutline, LibraryOutline, BookmarksOutline, SettingsOutline, ArchiveOutline, MenuOutline, Moon as MoonIcon, Sunny as SunnyIcon, PieChartOutline as EmbyStatsIcon } from '@vicons/ionicons5';
import axios from 'axios';
import logo from './assets/logo.png';

const message = useMessage();
const isMobile = ref(false);

const checkMobile = () => { isMobile.value = window.innerWidth < 768; };
onMounted(() => { checkMobile(); window.addEventListener('resize', checkMobile); });
onUnmounted(() => { window.removeEventListener('resize', checkMobile); });

const triggerStopTask = async () => {
  try {
    await axios.post('/api/trigger_stop_task');
    message.info('已发送停止任务请求。');
  } catch (error) { message.error(error.response?.data?.error || '请求失败。'); }
};

const props = defineProps({ isDark: Boolean, taskStatus: Object });
const emit = defineEmits(['update:is-dark']);

const router = useRouter(); 
const route = useRoute(); 
const authStore = useAuthStore();

const collapsed = ref(false); // 默认展开
const activeMenuKey = computed(() => route.name);
const appVersion = ref(__APP_VERSION__);

const isRealtimeLogVisible = ref(false);
const isHistoryLogVisible = ref(false);
const logRef = ref(null);

watch(() => route.path, () => { if (isMobile.value) collapsed.value = true; });

const renderIcon = (iconComponent) => () => h(NIcon, null, { default: () => h(iconComponent) });
const logContent = computed(() => props.taskStatus?.logs?.join('\n') || '等待任务日志...');

watch([() => props.taskStatus?.logs, isRealtimeLogVisible], async ([newLogs, isVisible], [oldLogs, wasVisible]) => {
    if (!isVisible) return;
    if (isVisible && !wasVisible) { setTimeout(() => { logRef.value?.scrollTo({ position: 'bottom', silent: true }); }, 150); return; }
    if (logRef.value) {
      const scrollEl = logRef.value.$el?.querySelector('.n-scrollbar-container') || logRef.value.$el;
      if (scrollEl && scrollEl.scrollHeight !== undefined) {
        if (scrollEl.scrollHeight - scrollEl.scrollTop <= scrollEl.clientHeight + 100) {
          await nextTick(); logRef.value?.scrollTo({ position: 'bottom', silent: true });
        }
      }
    }
}, { deep: true });

const userOptions = computed(() => [{ label: '退出登录', key: 'logout', icon: renderIcon(LogoutIcon) }]);

const handleUserSelect = async (key) => {
  if (key === 'logout') { await authStore.logout(); router.push({ name: 'Login' }); }
};

const menuOptions = computed(() => {
  const discoveryGroup = { label: '发现', key: 'group-discovery', icon: renderIcon(CompassOutline), children: [] };
  if (authStore.isAdmin) discoveryGroup.children.push({ label: '数据看板', key: 'DatabaseStats', icon: renderIcon(StatsIcon) });
  if (authStore.isLoggedIn) {
    discoveryGroup.children.push({ label: '用户中心', key: 'UserCenter', icon: renderIcon(UserCenterIcon) }, { label: '影视探索', key: 'Discover', icon: renderIcon(DiscoverIcon) });
    if (authStore.isAdmin) discoveryGroup.children.push({ label: '播放统计', key: 'EmbyStats', icon: renderIcon(EmbyStatsIcon) });
  }

  const finalMenu = [discoveryGroup];
  if (authStore.isAdmin) {
    finalMenu.push(
      { label: '整理', key: 'group-management', icon: renderIcon(LibraryOutline), children: [ 
          { label: '原生合集', key: 'Collections', icon: renderIcon(CollectionsIcon) }, 
          { label: '自建合集', key: 'CustomCollectionsManager', icon: renderIcon(CustomCollectionsIcon) }, 
          { label: '媒体去重', key: 'MediaCleanupPage', icon: renderIcon(CleanupIcon) },
          { label: '媒体整理', key: 'ResubscribePage', icon: renderIcon(ResubscribeIcon) },
          { label: '自动标签', key: 'AutoTaggingPage', icon: renderIcon(TagIcon) },
          { label: '手动处理', key: 'ReviewList', icon: renderIcon(ReviewListIcon) }, 
      ]},
      { label: '订阅', key: 'group-subscriptions', icon: renderIcon(BookmarksOutline), children: [ 
          { label: '智能追剧', key: 'Watchlist', icon: renderIcon(WatchlistIcon) }, 
          { label: '演员订阅', key: 'ActorSubscriptions', icon: renderIcon(ActorSubIcon) }, 
          { label: '统一订阅', key: 'UnifiedSubscriptions', icon: renderIcon(UnifiedSubIcon) },
      ]},
      { label: '系统', key: 'group-system', icon: renderIcon(SettingsOutline), children: [ 
          { label: '通用设置', key: 'settings-general', icon: renderIcon(GeneralIcon) }, 
          { label: '用户管理', key: 'UserManagement', icon: renderIcon(UserManagementIcon) },
          { label: '任务中心', key: 'settings-scheduler', icon: renderIcon(SchedulerIcon) },
          { label: '封面生成', key: 'CoverGeneratorConfig', icon: renderIcon(PaletteIcon) }, 
      ]}
    );
  }
  return finalMenu;
});

function handleMenuUpdate(key) { router.push({ name: key }); }
</script>

<style>
/* 全局布局与背景 */
.app-main-layout {
  height: 100vh;
  background: transparent !important;
}

.app-main-content {
  background: transparent !important;
  position: relative;
}

.page-content-inner-wrapper { height: 100%; overflow-y: auto; }

/* 玻璃拟态侧边栏 */
.glass-sider {
  background: var(--sider-bg) !important;
  backdrop-filter: blur(16px);
  -webkit-backdrop-filter: blur(16px);
  border-right: 1px solid var(--card-border-color);
  z-index: 10;
}

.sider-content-wrapper {
  display: flex;
  flex-direction: column;
  height: 100vh;
}

/* 侧边栏 Logo 区域 */
.sider-logo {
  padding: 30px 0 20px 0;
  display: flex;
  justify-content: center;
  align-items: center;
  transition: all 0.3s ease;
}
.sider-logo.collapsed { padding: 30px 0 20px 0; }
.logo-img { height: 48px; width: auto; max-width: 80%; object-fit: contain; filter: drop-shadow(0 2px 8px rgba(0,0,0,0.1)); transition: height 0.3s; }
.sider-logo.collapsed .logo-img { height: 32px; }

/* 中间菜单区弹性拉伸 */
.sider-menu-container {
  flex: 1;
  overflow: hidden;
}

.n-menu .n-menu-item-group-title { font-size: 12px; font-weight: 500; color: #8e8e93; padding-left: 24px; margin-top: 12px; margin-bottom: 4px; }
.n-menu .n-menu-item-group:first-child .n-menu-item-group-title { margin-top: 0; }

/* 底部工具栏 */
.sider-bottom-tools {
  padding: 16px;
  display: flex;
  flex-direction: column;
  gap: 12px;
}
.tools-actions-row {
  display: flex;
  justify-content: space-between;
  align-items: center;
}
.user-profile-btn {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 10px 12px;
  background: rgba(120, 120, 120, 0.1);
  border-radius: 8px;
  cursor: pointer;
  transition: background 0.2s;
}
.user-profile-btn:hover { background: rgba(120, 120, 120, 0.2); }
.username-text { font-size: 14px; font-weight: 500; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.app-version { text-align: center; font-size: 12px; color: #999; opacity: 0.6; }

/* 桌面端右上角悬浮任务胶囊 */
.floating-task-pill {
  position: absolute;
  top: 24px;
  right: 24px;
  z-index: 50;
  display: flex;
  align-items: center;
  background: var(--card-bg-color);
  backdrop-filter: blur(12px);
  -webkit-backdrop-filter: blur(12px);
  border: 1px solid var(--card-border-color);
  border-radius: 30px;
  padding: 6px 16px;
  box-shadow: 0 4px 20px var(--card-shadow-color);
  max-width: 400px;
}
.pill-icon { margin-right: 8px; }
.pill-text-area { display: flex; align-items: center; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; flex: 1; font-size: 13px; margin-right: 8px;}
.pill-divider { margin: 0 6px; opacity: 0.4; }
.pill-msg { opacity: 0.8; overflow: hidden; text-overflow: ellipsis; }
.pill-stop-btn { margin-left: 4px; }

/* 动画过渡 */
.fade-enter-active, .fade-leave-active { transition: opacity 0.3s, transform 0.3s; }
.fade-enter-from, .fade-leave-to { opacity: 0; transform: translateY(-10px); }

/* 移动端适配 */
@media (max-width: 768px) {
  .mobile-sider { position: absolute; left: 0; top: 0; bottom: 0; z-index: 1000; box-shadow: 2px 0 12px rgba(0,0,0,0.15); }
  .mobile-sider-mask { position: absolute; top: 0; left: 0; right: 0; bottom: 0; background-color: rgba(0,0,0,0.4); z-index: 999; backdrop-filter: blur(2px); }
  .n-layout-content .page-content-inner-wrapper { padding: 16px !important; padding-top: 60px !important; /* 留出悬浮按钮空间 */ }
  .mobile-menu-btn { position: absolute; top: 16px; left: 16px; z-index: 90; box-shadow: 0 2px 8px rgba(0,0,0,0.1); }
  .floating-task-pill { top: 16px; right: 16px; max-width: 60%; }
}
</style>