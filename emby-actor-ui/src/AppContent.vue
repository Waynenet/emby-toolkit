<!-- src/AppContent.vue -->
<template>
  <!-- 1. 如果需要后台布局，显示 MainLayout -->
  <MainLayout 
    v-if="showMainLayout"
    :is-dark="isDarkTheme" 
    :task-status="backgroundTaskStatus"
    @update:is-dark="handleModeChange"
  />
  
  <!-- ★★★ 核心修复点 ★★★ -->
  <!-- 2. 否则 (即公共页面)，用 .fullscreen-container 包裹 router-view -->
  <div v-else class="fullscreen-container">
    <router-view />
  </div>

  <div v-if="!isReady" class="fullscreen-container">
    <n-spin size="large" />
  </div>
</template>

<script setup>
import { ref, watch, onBeforeUnmount, onMounted, computed } from 'vue';
import { useRoute } from 'vue-router';
import { NSpin } from 'naive-ui';
import { useAuthStore } from './stores/auth';
import MainLayout from './MainLayout.vue';
import { appTheme } from './theme.js';
import axios from 'axios';

// --- 路由和认证 ---
const route = useRoute();
const authStore = useAuthStore();

// --- 布局决策 ---
const showMainLayout = computed(() => {
  return !route.meta.public;
});

// --- 下面的所有 script setup 内容都保持原样 ---
const isDarkTheme = ref(localStorage.getItem('isDark') === 'true');
const isReady = ref(false);

const backgroundTaskStatus = ref({ is_running: false, current_action: '空闲' });
let statusIntervalId = null;

const app = document.getElementById('app');

const applyTheme = (isDark) => {
  const root = document.documentElement;
  const themeMode = isDark ? 'dark' : 'light';
  const themeConfig = appTheme[themeMode];

  app.dispatchEvent(new CustomEvent('update-naive-theme', { detail: themeConfig.naive }));
  for (const key in themeConfig.custom) {
    root.style.setProperty(key, themeConfig.custom[key]);
  }
  root.classList.remove('dark', 'light');
  root.classList.add(isDark ? 'dark' : 'light');
};

const handleModeChange = (isDark) => {
  isDarkTheme.value = isDark;
  localStorage.setItem('isDark', String(isDark));
  app.dispatchEvent(new CustomEvent('update-dark-mode', { detail: isDark }));
};

watch(isDarkTheme, (isDark) => {
  applyTheme(isDark);
}, { deep: true });

watch(() => authStore.isLoggedIn, (isLoggedIn) => {
  if (isLoggedIn) {
    if (!statusIntervalId) {
      const fetchStatus = async () => {
        try {
          const response = await axios.get('/api/status');
          backgroundTaskStatus.value = response.data;
        } catch (error) { console.error('获取状态失败:', error); }
      };
      fetchStatus();
      statusIntervalId = setInterval(fetchStatus, 2000);
    }
  } else {
    if (statusIntervalId) { clearInterval(statusIntervalId); statusIntervalId = null; }
  }
}, { immediate: true });

onMounted(async () => {
  try {
    await axios.get('/api/config');
  } catch (error) {
    console.error("加载初始配置失败:", error);
  } finally {
    localStorage.removeItem('user-theme');
    applyTheme(isDarkTheme.value);
    isReady.value = true;
  }
});

onBeforeUnmount(() => {
  if (statusIntervalId) clearInterval(statusIntervalId);
});
</script>