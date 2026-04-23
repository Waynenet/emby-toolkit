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
import axios from 'axios';

const route = useRoute();
const authStore = useAuthStore();

const showMainLayout = computed(() => !route.meta.public);

const isDarkTheme = ref(localStorage.getItem('isDark') === 'true');
const isReady = ref(false);
const backgroundTaskStatus = ref({ is_running: false, current_action: '空闲' });
let statusIntervalId = null;

const app = document.getElementById('app');

// ★★★ 核心：Naive UI 毛玻璃主题覆盖配置 ★★★
const glassmorphismOverrides = {
  common: {
    baseColor: '#fff',
    primaryColor: '#8a2be2', // 紫色系主色调
    primaryColorHover: '#9b4dec',
    textColor1: 'rgba(255, 255, 255, 0.95)',
    textColor2: 'rgba(255, 255, 255, 0.75)',
    textColor3: 'rgba(255, 255, 255, 0.5)',
    dividerColor: 'rgba(255, 255, 255, 0.1)',
    bodyColor: 'transparent',
    cardColor: 'transparent',
    modalColor: 'rgba(30, 35, 45, 0.85)',
    popoverColor: 'rgba(30, 35, 45, 0.85)',
  },
  Card: {
    color: 'transparent',
    borderColor: 'transparent',
  },
  Input: {
    color: 'rgba(255, 255, 255, 0.05)',
    colorFocus: 'rgba(255, 255, 255, 0.1)',
    border: '1px solid rgba(255, 255, 255, 0.1)',
    borderFocus: '1px solid rgba(255, 255, 255, 0.3)',
    textColor: '#fff',
    borderRadius: '8px'
  },
  Select: {
    peers: {
      InternalSelection: {
        color: 'rgba(255, 255, 255, 0.05)',
        colorActive: 'rgba(255, 255, 255, 0.1)',
        border: '1px solid rgba(255, 255, 255, 0.1)',
        borderActive: '1px solid rgba(255, 255, 255, 0.3)',
        textColor: '#fff',
        borderRadius: '8px'
      }
    }
  },
  Button: {
    colorOpacitySecondary: '0.1',
    colorOpacitySecondaryHover: '0.2',
    textColor: '#fff',
    borderRadius: '8px'
  },
  Menu: {
    itemColorHover: 'rgba(255, 255, 255, 0.1)',
    itemColorActive: 'rgba(255, 255, 255, 0.15)',
    itemTextColor: 'rgba(255, 255, 255, 0.75)',
    itemTextColorActive: '#fff',
    itemIconColor: 'rgba(255, 255, 255, 0.75)',
    itemIconColorActive: '#fff',
    borderRadius: '12px'
  }
};

const applyTheme = (isDark) => {
  const root = document.documentElement;
  // 发送毛玻璃配置给 App.vue
  app.dispatchEvent(new CustomEvent('update-naive-theme', { detail: glassmorphismOverrides }));
  
  root.classList.remove('dark', 'light');
  root.classList.add('dark'); // 强制暗色模式底色
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

onMounted(() => {
  applyTheme(isDarkTheme.value);
  isReady.value = true;
});

onBeforeUnmount(() => {
  if (statusIntervalId) clearInterval(statusIntervalId);
});
</script>

<style scoped>
.loader-container {
  position: absolute;
  top: 0;
  left: 0;
  z-index: 9999;
  background: transparent;
  backdrop-filter: blur(20px);
}
</style>