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
        <!-- 顶部 Logo (模块化透明) -->
        <div class="sider-logo-module" :class="{ 'collapsed': collapsed && !isMobile }">
          <img :src="logo" alt="Logo" class="logo-img" />
        </div>

        <!-- 中间 导航菜单 (可滚动) -->
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

        <!-- 底部 版本号 (固定小模块) -->
        <div class="sider-bottom-module" v-show="!collapsed || isMobile">
          <div class="version-pill">v{{ appVersion }}</div>
        </div>
      </div>
    </n-layout-sider>

    <!-- 右侧内容区 -->
    <n-layout-content class="app-main-content" :native-scrollbar="true">
      
      <!-- ★★★ 右上角模块化工具栏 ★★★ -->
      <div class="top-header-bar">
        <div class="header-left">
          <n-button v-if="isMobile" circle class="glass-btn" @click="collapsed = !collapsed">
            <template #icon><n-icon :component="MenuOutline" /></template>
          </n-button>
        </div>
        
        <div class="header-right">
          <!-- 任务状态胶囊 -->
          <transition name="fade">
            <div v-if="authStore.isAdmin && props.taskStatus && props.taskStatus.current_action !== '空闲' && props.taskStatus.current_action !== '无'" class="glass-module task-pill">
              <n-spin v-if="props.taskStatus.is_running" size="small" style="margin-right: 8px;" />
              <n-icon v-else :component="SchedulerIcon" style="margin-right: 8px; opacity: 0.6;" />
              <span class="task-text">{{ props.taskStatus.current_action }} - {{ props.taskStatus.message }}</span>
              <div class="action-icon-btn" v-if="props.taskStatus.is_running" @click="triggerStopTask" style="margin-left: 8px; color: #e88080;">
                <n-icon :component="StopIcon" size="18" />
              </div>
            </div>
          </transition>

          <!-- 主题切换 -->
          <div class="glass-module icon-module">
            <n-switch :value="props.isDark" @update:value="newValue => emit('update:is-dark', newValue)" size="small">
              <template #checked-icon><n-icon :component="MoonIcon" /></template>
              <template #unchecked-icon><n-icon :component="SunnyIcon" /></template>
            </n-switch>
          </div>

          <!-- ★★★ 修复：日志按钮，改用原生 div 绑定 click 防止事件被吞 ★★★ -->
          <div v-if="authStore.isAdmin" class="glass-module icon-module">
            <n-tooltip>
              <template #trigger>
                <div class="action-icon-btn" @click="isRealtimeLogVisible = true">
                  <n-icon size="20" :component="ReaderOutline" />
                </div>
              </template>
              实时日志
            </n-tooltip>
            
            <n-divider vertical style="margin: 0 8px; opacity: 0.3;" />
            
            <n-tooltip>
              <template #trigger>
                <div class="action-icon-btn" @click="isHistoryLogVisible = true">
                  <n-icon size="20" :component="ArchiveOutline" />
                </div>
              </template>
              历史日志
            </n-tooltip>
          </div>

          <!-- 用户中心 -->
          <n-dropdown v-if="authStore.isLoggedIn" trigger="hover" placement="bottom-end" :options="userOptions" @select="handleUserSelect">
            <div class="glass-module user-module">
              <n-icon size="18" :component="UserCenterIcon" style="margin-right: 6px;" />
              <span>{{ authStore.username }}</span>
            </div>
          </n-dropdown>
        </div>
      </div>

      <!-- 路由页面内容 -->
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
import { NLayout, NLayoutSider, NLayoutContent, NMenu, NSwitch, NIcon, NModal, NDropdown, NButton, NTooltip, NLog, useMessage, NDivider, NSpin } from 'naive-ui';
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

.sider-logo-module {
  padding: 24px 0;
  display: flex; justify-content: center; align-items: center;
  flex-shrink: 0; 
}
.sider-logo-module.collapsed { padding: 24px 0; }
.logo-img { height: 48px; width: auto; max-width: 80%; object-fit: contain; filter: drop-shadow(0 2px 8px rgba(0,0,0,0.2)); transition: height 0.3s; }
.sider-logo-module.collapsed .logo-img { height: 32px; }

.sider-menu-container {
  flex: 1; 
  overflow-y: auto; 
  overflow-x: hidden;
  padding: 0 12px; 
}
.n-menu-item { margin-top: 4px; }
.n-menu .n-menu-item-group-title { font-size: 12px; font-weight: 500; color: var(--text-secondary); padding-left: 24px; margin-top: 12px; margin-bottom: 4px; }

.sider-bottom-module {
  padding: 16px;
  display: flex;
  justify-content: center;
  flex-shrink: 0; 
}
.version-pill {
  background: var(--glass-border);
  padding: 4px 12px;
  border-radius: 20px;
  font-size: 12px;
  color: var(--text-secondary);
  font-family: monospace;
  border: 1px solid var(--glass-border-light);
}

/* ★★★ 右上角工具栏 ★★★ */
.top-header-bar {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 0 0 16px 0;
  flex-shrink: 0;
}
.header-right {
  display: flex;
  gap: 12px;
  align-items: center;
  margin-left: auto;
}

.glass-module {
  background: var(--glass-bg);
  backdrop-filter: var(--glass-blur);
  -webkit-backdrop-filter: var(--glass-blur);
  border: 1px solid var(--glass-border);
  border-radius: 12px;
  padding: 6px 12px;
  display: flex;
  align-items: center;
  box-shadow: var(--glass-shadow);
  color: var(--text-primary);
}
.icon-module { padding: 6px 10px; }
.user-module { cursor: pointer; font-weight: 500; font-size: 14px; transition: background 0.2s; }
.user-module:hover { background: var(--glass-bg-hover); }

/* ★★★ 修复：自定义图标按钮，防止事件被吞 ★★★ */
.action-icon-btn {
  cursor: pointer;
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 4px;
  border-radius: 6px;
  transition: background-color 0.2s;
}
.action-icon-btn:hover {
  background-color: rgba(255, 255, 255, 0.1);
}

.task-pill { max-width: 300px; }
.task-text { white-space: nowrap; overflow: hidden; text-overflow: ellipsis; font-size: 13px; }

.glass-btn {
  background: var(--glass-bg) !important;
  border: 1px solid var(--glass-border) !important;
  color: var(--text-primary) !important;
  backdrop-filter: var(--glass-blur);
}

.page-content-inner-wrapper { flex: 1; overflow-y: auto; }

.fade-enter-active, .fade-leave-active { transition: opacity 0.3s, transform 0.3s; }
.fade-enter-from, .fade-leave-to { opacity: 0; transform: translateY(-10px); }

@media (max-width: 768px) {
  .app-main-layout { padding: 0; }
  .app-main-content { margin-left: 0; border-radius: 0; padding: 12px !important; }
  .glass-sider { height: 100vh !important; border-radius: 0; }
  .mobile-sider { position: absolute; left: 0; top: 0; bottom: 0; z-index: 1000; box-shadow: 2px 0 12px rgba(0,0,0,0.5); }
  .mobile-sider-mask { position: absolute; top: 0; left: 0; right: 0; bottom: 0; background-color: rgba(0,0,0,0.6); z-index: 999; backdrop-filter: blur(4px); }
  .top-header-bar { padding-bottom: 12px; }
  .task-pill { display: none; }
}
</style>