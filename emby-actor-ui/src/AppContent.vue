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
  
  <div v-if="!isReady" class="fullscreen-container loader-container">
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

// 路由判断：如果是 public 页面（如登录），就不显示主框架
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

  // 1. 发送 Naive UI 的主题配置
  app.dispatchEvent(new CustomEvent('update-naive-theme', { detail: themeConfig.naive }));
  
  // 2. 仅仅向 :root 注入 CSS 变量，具体的渲染工作交给 App.vue 的 <style> 去完成
  for (const key in themeConfig.custom) {
    root.style.setProperty(key, themeConfig.custom[key]);
  }

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

// 监听任务状态 (登录后开始轮询)
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

<style scoped>
/* 保证初始化加载动画时的背景平滑 */
.loader-container {
  position: absolute;
  top: 0;
  left: 0;
  z-index: 9999;
  background: var(--global-bg);
}
</style>