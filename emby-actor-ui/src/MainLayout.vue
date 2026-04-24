<!-- src/MainLayout.vue -->
<template>
  <n-layout has-sider class="app-main-layout">
    <div v-if="isMobile && !collapsed" class="mobile-sider-mask" @click="collapsed = true"></div>

    <!-- 侧边栏：背景全透明，内容模块化 -->
    <n-layout-sider
      :bordered="false"
      collapse-mode="width"
      :collapsed-width="isMobile ? 0 : 64"
      :width="210"
      :show-trigger="isMobile ? false : 'bar'"
      :native-scrollbar="false"
      :collapsed="collapsed"
      @update:collapsed="val => collapsed = val"
      :class="['transparent-sider', { 'mobile-sider': isMobile }]"
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
            class="modular-menu"
          />
        </div>

        <!-- 底部 版本号小模块 -->
        <div class="sider-bottom-tools" v-show="!collapsed || isMobile">
          <div class="version-module">
            v{{ appVersion }}
          </div>
        </div>
      </div>
    </n-layout-sider>

    <!-- 右侧主内容区 -->
    <n-layout-content class="app-main-content" :native-scrollbar="false">
      
      <!-- ★★★ macOS 风格顶部状态栏 ★★★ -->
      <div class="macos-status-bar">
        <div class="status-left">
          <n-button v-if="isMobile" circle class="mobile-menu-btn" @click="collapsed = !collapsed" size="small">
            <template #icon><n-icon :component="MenuOutline" /></template>
          </n-button>
        </div>
        
        <!-- 居中：任务胶囊 -->
        <div class="status-center">
          <transition name="fade">
            <div v-if="authStore.isAdmin && props.taskStatus && props.taskStatus.current_action !== '空闲' && props.taskStatus.current_action !== '无'" class="status-pill task-pill">
              <n-spin v-if="props.taskStatus.is_running" size="small" class="pill-icon" />
              <n-icon v-else :component="SchedulerIcon" class="pill-icon" />
              <div class="pill-text">
                <strong :style="{ color: props.taskStatus.is_running ? 'var(--n-primary-color)' : 'inherit' }">{{ props.taskStatus.current_action }}</strong>
                <span style="margin: 0 6px; opacity: 0.5;">-</span>
                <span style="opacity: 0.8;">{{ props.taskStatus.message }}</span>
              </div>
              <n-button v-if="props.taskStatus.is_running" type="error" size="tiny" circle secondary @click="triggerStopTask" style="margin-left: 8px;">
                <template #icon><n-icon :component="StopIcon" /></template>
              </n-button>
            </div>
          </transition>
        </div>

        <!-- 右侧：工具与用户模块 -->
        <div class="status-right">
          <div class="status-pill tools-pill" v-if="authStore.isAdmin">
            <n-tooltip><template #trigger><n-button @click="isRealtimeLogVisible = true" circle text><template #icon><n-icon :component="ReaderOutline" /></template></n-button></template>实时日志</n-tooltip>
            <div class="divider-v"></div>
            <n-tooltip><template #trigger><n-button @click="isHistoryLogVisible = true" circle text><template #icon><n-icon :component="ArchiveOutline" /></template></n-button></template>历史日志</n-tooltip>
            <div class="divider-v"></div>
            <n-switch :value="props.isDark" @update:value="newValue => emit('update:is-dark', newValue)" size="small">
              <template #checked-icon><n-icon :component="MoonIcon" /></template>
              <template #unchecked-icon><n-icon :component="SunnyIcon" /></template>
            </n-switch>
          </div>

          <n-dropdown v-if="authStore.isLoggedIn" trigger="hover" placement="bottom-end" :options="userOptions" @select="handleUserSelect">
            <div class="status-pill user-pill">
              <n-icon size="16" :component="UserCenterIcon" />
              <span>{{ authStore.username }}</span>
            </div>
          </n-dropdown>
        </div>
      </div>

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
import { NLayout, NLayoutSider, NLayoutContent, NMenu, NSwitch, NIcon, NModal, NDropdown, NButton, NTooltip, NLog, useMessage, NSpin } from 'naive-ui';
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
  display: flex;
}

/* ★ 侧边栏完全透明，融入背景 ★ */
.transparent-sider {
  background: transparent !important;
  z-index: 10;
  height: 100vh !important; 
}

:deep(.n-layout-sider-scroll-container) {
  display: flex !important;
  flex-direction: column !important;
  height: 100% !important;
  overflow: hidden !important; 
  border-right: none !important;
}

.sider-content-wrapper { display: flex; flex-direction: column; height: 100%; width: 100%; }

.sider-logo { padding: 24px 0; display: flex; justify-content: center; align-items: center; flex-shrink: 0; }
.logo-img { height: 48px; max-width: 80%; object-fit: contain; filter: drop-shadow(0 2px 8px rgba(0,0,0,0.2)); transition: height 0.3s; }
.sider-logo.collapsed .logo-img { height: 32px; }

/* 菜单模块化 */
.sider-menu-container { flex: 1; overflow-y: auto; overflow-x: hidden; padding: 0 12px; }
.modular-menu .n-menu-item { margin-top: 6px; }
.modular-menu .n-menu-item-content { border-radius: 12px !important; }
.modular-menu .n-menu-item-group-title { font-size: 12px; font-weight: bold; color: var(--text-secondary); padding-left: 16px; margin-top: 16px; margin-bottom: 4px; }

/* 底部版本号模块 */
.sider-bottom-tools { padding: 16px; display: flex; justify-content: center; flex-shrink: 0; }
.version-module {
  background: var(--glass-bg); backdrop-filter: var(--glass-blur); -webkit-backdrop-filter: var(--glass-blur);
  border: 1px solid var(--glass-border); border-radius: 20px; padding: 4px 16px;
  font-size: 12px; color: var(--text-secondary); font-family: monospace; font-weight: bold;
}

/* ★ 主内容区 & macOS 状态栏 ★ */
.app-main-content {
  background: transparent !important;
  display: flex;
  flex-direction: column;
  height: 100vh;
}

.macos-status-bar {
  display: flex; justify-content: space-between; align-items: center;
  padding: 16px 24px 0 24px; flex-shrink: 0;
}

.status-left, .status-center, .status-right { display: flex; align-items: center; gap: 12px; }
.status-center { flex: 1; justify-content: center; }

/* 状态栏胶囊模块 */
.status-pill {
  display: flex; align-items: center; gap: 8px;
  background: var(--glass-bg); backdrop-filter: var(--glass-blur); -webkit-backdrop-filter: var(--glass-blur);
  border: 1px solid var(--glass-border); border-radius: 30px; padding: 6px 16px;
  box-shadow: var(--glass-shadow); color: var(--text-primary); font-size: 13px; font-weight: 500;
}
.tools-pill { padding: 4px 12px; }
.user-pill { cursor: pointer; transition: background 0.2s; }
.user-pill:hover { background: var(--glass-bg-hover); }

.divider-v { width: 1px; height: 14px; background: var(--glass-border-light); margin: 0 4px; }

.pill-text { display: flex; align-items: center; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; max-width: 300px; }

.page-content-inner-wrapper { flex: 1; overflow-y: auto; padding: 16px 24px 24px 24px; }

.fade-enter-active, .fade-leave-active { transition: opacity 0.3s, transform 0.3s; }
.fade-enter-from, .fade-leave-to { opacity: 0; transform: translateY(-10px); }

@media (max-width: 768px) {
  .macos-status-bar { padding: 12px 16px 0 16px; }
  .page-content-inner-wrapper { padding: 12px 16px 16px 16px; }
  .mobile-sider { position: absolute; left: 0; top: 0; bottom: 0; z-index: 1000; background: var(--glass-bg) !important; backdrop-filter: var(--glass-blur); border-right: 1px solid var(--glass-border); }
  .mobile-sider-mask { position: absolute; top: 0; left: 0; right: 0; bottom: 0; background-color: rgba(0,0,0,0.6); z-index: 999; backdrop-filter: blur(4px); }
  .status-pill { padding: 4px 10px; font-size: 12px; }
  .pill-text { max-width: 150px; }
}
</style>