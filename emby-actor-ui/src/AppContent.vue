<!-- src/AppContent.vue -->
<template>
  <MainLayout 
    v-if="showMainLayout"
    :is-dark="isDarkTheme" 
    :task-status="backgroundTaskStatus"
    @update:is-dark="handleModeChange"
  />
  
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
import { modernTheme } from './theme.js';
import axios from 'axios';

const route = useRoute();
const authStore = useAuthStore();

const showMainLayout = computed(() => !route.meta.public);

const isDarkTheme = ref(localStorage.getItem('isDark') === 'true');
const isReady = ref(false);
const backgroundTaskStatus = ref({ is_running: false, current_action: '空闲' });
let statusIntervalId = null;

const app = document.getElementById('app');

const applyTheme = (isDark) => {
  const root = document.documentElement;
  const themeMode = isDark ? 'dark' : 'light';
  const themeConfig = modernTheme[themeMode];

  app.dispatchEvent(new CustomEvent('update-naive-theme', { detail: themeConfig.naive }));
  
  for (const key in themeConfig.custom) {
    root.style.setProperty(key, themeConfig.custom[key]);
  }
  
  // 注入全局柔和渐变背景
  document.body.style.background = themeConfig.custom['--global-bg'];
  document.body.style.backgroundAttachment = 'fixed';
  document.body.style.minHeight = '100vh';
  document.body.style.transition = 'background 0.5s ease';

  root.classList.remove('dark', 'light');
  root.classList.add(themeMode);
};

const handleModeChange = (isDark) => {
  isDarkTheme.value = isDark;
  localStorage.setItem('isDark', String(isDark));
  app.dispatchEvent(new CustomEvent('update-dark-mode', { detail: isDark }));
};

// 监听明暗模式变化
watch(isDarkTheme, (isDark) => {
  applyTheme(isDark);
}, { deep: true });

// 监听任务状态
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

onMounted(() => {
  applyTheme(isDarkTheme.value);
  isReady.value = true;
});

onBeforeUnmount(() => {
  if (statusIntervalId) clearInterval(statusIntervalId);
});
</script>

<style>
/* 针对非 MainLayout (如登录界面) 的透明化处理 */
.fullscreen-container {
  min-height: 100vh;
  display: flex;
  align-items: center;
  justify-content: center;
  background: transparent;
}
</style>