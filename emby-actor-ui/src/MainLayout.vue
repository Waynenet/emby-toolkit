<!-- src/MainLayout.vue -->
<template>
  <n-layout has-sider class="app-main-layout">
    <div v-if="isMobile && !collapsed" class="mobile-sider-mask" @click="collapsed = true"></div>

    <!-- 侧边栏 (玻璃拟态) -->
    <n-layout-sider
      :bordered="false"
      collapse-mode="width"
      :collapsed-width="isMobile ? 0 : 64"
      :width="210"
      :show-trigger="isMobile ? false : 'bar'"
      :native-scrollbar="true" 
      :collapsed="collapsed"
      @update:collapsed="val => collapsed = val"
      :class="['glass-sider', { 'mobile-sider': isMobile }]"
    >
      <div class="sider-content-wrapper">
        <!-- 顶部 Logo -->
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

        <!-- 底部 版本号模块 -->
        <div class="sider-bottom-tools" v-show="!collapsed || isMobile">
          <div class="version-module">
            <span class="app-version">v{{ appVersion }}</span>
          </div>
        </div>
      </div>
    </n-layout-sider>

    <!-- 右侧内容区 -->
    <n-layout-content class="app-main-content" :native-scrollbar="true">
      
      <!-- 顶部模块化操作栏 -->
      <div class="top-header-bar">
        <!-- 左侧：移动端菜单按钮 -->
        <div class="header-left">
          <div v-if="isMobile" class="header-module icon-module" @click="collapsed = !collapsed">
            <n-icon :component="MenuOutline" size="20" />
          </div>
        </div>

        <!-- 右侧：操作模块 -->
        <div class="header-right">
          <!-- 主题切换模块 -->
          <div class="header-module icon-module" @click="emit('update:is-dark', !props.isDark)">
            <n-icon :component="props.isDark ? MoonIcon : SunnyIcon" size="18" />
          </div>

          <!-- 日志模块 -->
          <div v-if="authStore.isAdmin" class="header-module log-module">
            <div class="log-btn" @click="isRealtimeLogVisible = true">
              <n-icon :component="ReaderOutline" size="18" />
              <span v-if="!isMobile">实时</span>
            </div>
            <div class="module-divider"></div>
            <div class="log-btn" @click="isHistoryLogVisible = true">
              <n-icon :component="ArchiveOutline" size="18" />
              <span v-if="!isMobile">历史</span>
            </div>
          </div>

          <!-- 用户模块 -->
          <n-dropdown v-if="authStore.isLoggedIn" trigger="hover" placement="bottom-end" :options="userOptions" @select="handleUserSelect">
            <div class="header-module user-module">
              <n-icon size="18" :component="UserCenterIcon" />
              <span v-if="!isMobile" class="username-text">{{ authStore.username }}</span>
            </div>
          </n-dropdown>
        </div>
      </div>

      <!-- 悬浮任务状态胶囊 -->
      <transition name="fade">
        <div v-if="!isMobile && authStore.isAdmin && props.taskStatus && props.taskStatus.current_action !== '空闲' && props.taskStatus.current_action !== '无'" class="floating-task-pill">
          <n-spin v-if="props.taskStatus.is_running" size="small" class="pill-icon" />
          <n-icon v-else :component="SchedulerIcon" class="pill-icon" style="opacity: 0.6;" />
          <div class="pill-text-area">
            <strong :style="{ color: props.taskStatus.is_running ? 'var(--n-primary-color)' : 'inherit' }">{{ props.taskStatus.current_action }}</strong>
            <span class="pill-divider">-</span>
            <span class="pill-msg">{{ props.taskStatus.message }}</span>
          </div>
          <n-button v-if="props.taskStatus.is_running" type="error" size="tiny" circle secondary @click="triggerStopTask" class="pill-stop-btn">
            <template #icon><n-icon :component="StopIcon" /></template>
          </n-button>
        </div>
      </transition>

      <!-- 路由视图 -->
      <div class="page-content-inner-wrapper">
        <router-view v-slot="slotProps">
          <component :is="slotProps.Component" :task-status="props.taskStatus" />
        </router-view>
      </div>
    </n-layout-content>
    
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
  try { await axios.post('/api/trigger_stop_task'); message.info('已发送停止任务请求。'); } catch (error) { message.error(error.response?.data?.error || '请求失败。'); }
};

const props = defineProps({ isDark: Boolean, taskStatus: Object });
const emit = defineEmits(['update:is-dark']);
const router = useRouter(); 
const route = useRoute(); 
const authStore = useAuthStore();
const collapsed = ref(false); 
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
const handleUserSelect = async (key) => { if (key === 'logout') { await authStore.logout(); router.push({ name: 'Login' }); } };

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
.app-main-layout {
  height: 100vh;
  background: transparent !important;
  padding: 16px; 
  box-sizing: border-box;
}

.app-main-content {
  background: transparent !important;
  position: relative;
  margin-left: 16px; 
  border-radius: 16px;
  display: flex;
  flex-direction: column;
}

.page-content-inner-wrapper { 
  flex: 1;
  overflow-y: auto; 
}

.glass-sider {
  background: var(--glass-bg) !important;
  backdrop-filter: var(--glass-blur);
  -webkit-backdrop-filter: var(--glass-blur);
  border: 1px solid var(--glass-border);
  border-radius: 16px; 
  box-shadow: var(--glass-shadow);
  z-index: 10;
  height: calc(100vh - 32px) !important; 
}

:deep(.n-layout-sider-scroll-container) {
  display: flex !important;
  flex-direction: column !important;
  height: 100% !important;
  overflow: hidden !important; 
  border-right: none !important;
}

.sider-content-wrapper {
  display: flex;
  flex-direction: column;
  height: 100%;
  width: 100%;
}

.sider-logo {
  padding: 30px 0 20px 0;
  display: flex; justify-content: center; align-items: center;
  flex-shrink: 0; 
}
.sider-logo.collapsed { padding: 30px 0 20px 0; }
.logo-img { height: 48px; width: auto; max-width: 80%; object-fit: contain; filter: drop-shadow(0 2px 8px rgba(0,0,0,0.1)); transition: height 0.3s; }
.sider-logo.collapsed .logo-img { height: 32px; }

/* ★★★ 强制覆盖侧边栏所有文字颜色为纯白 ★★★ */
.sider-menu-container {
  flex: 1; 
  overflow-y: auto; 
  overflow-x: hidden;
  padding: 0 12px; 
}
.n-menu-item { margin-top: 4px; }
.n-menu .n-menu-item-group-title { font-size: 12px; font-weight: 500; color: rgba(255,255,255,0.6); padding-left: 24px; margin-top: 12px; margin-bottom: 4px; }
.n-menu .n-menu-item-group:first-child .n-menu-item-group-title { margin-top: 0; }

/* 强制覆盖菜单文字颜色为白色 */
.glass-sider .n-menu .n-menu-item-content__title,
.glass-sider .n-menu .n-menu-item-content__icon {
  color: rgba(255, 255, 255, 0.85) !important;
}
.glass-sider .n-menu .n-menu-item--selected .n-menu-item-content__title,
.glass-sider .n-menu .n-menu-item--selected .n-menu-item-content__icon {
  color: #fff !important;
}

.sider-bottom-tools {
  padding: 16px;
  display: flex;
  justify-content: center;
  flex-shrink: 0; 
}
.version-module {
  background: var(--glass-border);
  padding: 4px 12px;
  border-radius: 20px;
  border: 1px solid var(--glass-border-light);
}
.app-version { font-size: 12px; color: rgba(255,255,255,0.6); font-family: monospace; font-weight: bold; }

/* 顶部模块化操作栏 */
.top-header-bar {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 0 24px 16px 24px;
  flex-shrink: 0;
}
.header-left, .header-right {
  display: flex;
  align-items: center;
  gap: 12px;
}
.header-module {
  background: var(--glass-bg);
  backdrop-filter: var(--glass-blur);
  -webkit-backdrop-filter: var(--glass-blur);
  border: 1px solid var(--glass-border);
  box-shadow: var(--glass-shadow);
  border-radius: 12px;
  display: flex;
  align-items: center;
  color: var(--text-primary);
  transition: all 0.2s;
  cursor: pointer;
  height: 36px; 
}
.header-module:hover {
  background: var(--glass-bg-hover);
  border-color: var(--glass-border-light);
  transform: translateY(-2px);
}
.icon-module {
  padding: 0 10px;
  justify-content: center;
}

.log-module {
  padding: 0 12px;
  gap: 8px;
}
.log-btn {
  display: flex;
  align-items: center;
  gap: 4px;
  font-size: 13px;
  color: inherit;
}
.log-btn:hover {
  opacity: 0.8;
}
.module-divider {
  width: 1px;
  height: 14px;
  background: var(--glass-border-light);
}

.user-module {
  padding: 0 12px;
  gap: 8px;
}
.username-text {
  font-size: 13px;
  font-weight: 600;
}

.floating-task-pill {
  position: absolute; top: 60px; left: 50%; transform: translateX(-50%); z-index: 50; 
  display: flex; align-items: center;
  background: var(--glass-bg); backdrop-filter: var(--glass-blur); -webkit-backdrop-filter: var(--glass-blur);
  border: 1px solid var(--glass-border); border-radius: 30px; padding: 6px 16px;
  box-shadow: var(--glass-shadow); max-width: 400px; color: var(--text-primary);
}
.pill-icon { margin-right: 8px; }
.pill-text-area { display: flex; align-items: center; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; flex: 1; font-size: 13px; margin-right: 8px;}
.pill-divider { margin: 0 6px; opacity: 0.4; }
.pill-msg { opacity: 0.8; overflow: hidden; text-overflow: ellipsis; }
.pill-stop-btn { margin-left: 4px; }

.fade-enter-active, .fade-leave-active { transition: opacity 0.3s, transform 0.3s; }
.fade-enter-from, .fade-leave-to { opacity: 0; transform: translateY(-10px); }

@media (max-width: 768px) {
  .app-main-layout { padding: 0; }
  .app-main-content { margin-left: 0; border-radius: 0; }
  .glass-sider { height: 100vh !important; border-radius: 0; }
  .mobile-sider { position: absolute; left: 0; top: 0; bottom: 0; z-index: 1000; box-shadow: 2px 0 12px rgba(0,0,0,0.5); }
  .mobile-sider-mask { position: absolute; top: 0; left: 0; right: 0; bottom: 0; background-color: rgba(0,0,0,0.6); z-index: 999; backdrop-filter: blur(4px); }
  .n-layout-content .page-content-inner-wrapper { padding: 0 12px !important; }
  .top-header-bar { padding: 16px 12px; }
  .floating-task-pill { top: 70px; left: 50%; transform: translateX(-50%); max-width: 85%; }
}
</style>