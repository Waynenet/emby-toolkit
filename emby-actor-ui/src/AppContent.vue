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

// 动态生成 Naive UI 覆盖配置
const getThemeOverrides = (isDark) => {
  const textColor = isDark ? 'rgba(255, 255, 255, 0.95)' : 'rgba(0, 0, 0, 0.85)';
  const textColor2 = isDark ? 'rgba(255, 255, 255, 0.75)' : 'rgba(0, 0, 0, 0.65)';
  const inputBg = isDark ? 'rgba(255, 255, 255, 0.05)' : 'rgba(0, 0, 0, 0.05)';
  const inputBgActive = isDark ? 'rgba(255, 255, 255, 0.1)' : 'rgba(0, 0, 0, 0.1)';
  const borderColor = isDark ? 'rgba(255, 255, 255, 0.1)' : 'rgba(0, 0, 0, 0.1)';
  
  return {
    common: {
      primaryColor: '#8a2be2',
      primaryColorHover: '#9b4dec',
      textColor1: textColor,
      textColor2: textColor2,
      textColor3: isDark ? 'rgba(255, 255, 255, 0.5)' : 'rgba(0, 0, 0, 0.4)',
      dividerColor: borderColor,
      bodyColor: 'transparent',
      cardColor: 'transparent',
      modalColor: isDark ? 'rgba(30, 35, 45, 0.85)' : 'rgba(255, 255, 255, 0.85)',
      popoverColor: isDark ? 'rgba(30, 35, 45, 0.85)' : 'rgba(255, 255, 255, 0.85)',
    },
    Card: { color: 'transparent', borderColor: 'transparent' },
    Input: {
      color: inputBg, colorFocus: inputBgActive,
      border: `1px solid ${borderColor}`, borderFocus: `1px solid #8a2be2`,
      textColor: textColor, borderRadius: '8px'
    },
    Select: {
      peers: {
        InternalSelection: {
          color: inputBg, colorActive: inputBgActive,
          border: `1px solid ${borderColor}`, borderActive: `1px solid #8a2be2`,
          textColor: textColor, borderRadius: '8px'
        }
      }
    },
    Button: { textColor: textColor, borderRadius: '8px' },
    Menu: {
      itemColorHover: inputBg, itemColorActive: inputBgActive,
      itemTextColor: textColor2, itemTextColorActive: textColor,
      itemIconColor: textColor2, itemIconColorActive: textColor,
      borderRadius: '12px'
    }
  };
};

const applyTheme = (isDark) => {
  const root = document.documentElement;
  app.dispatchEvent(new CustomEvent('update-naive-theme', { detail: getThemeOverrides(isDark) }));
  
  root.classList.remove('dark', 'light');
  root.classList.add(isDark ? 'dark' : 'light');
};

const handleModeChange = (isDark) => {
  isDarkTheme.value = isDark;
  localStorage.setItem('isDark', String(isDark));
  app.dispatchEvent(new CustomEvent('update-dark-mode', { detail: isDark }));
};

watch(isDarkTheme, (isDark) => { applyTheme(isDark); }, { deep: true });

watch(() => authStore.isLoggedIn, (isLoggedIn) => {
  if (isLoggedIn) {
    if (!statusIntervalId) {
      const fetchStatus = async () => {
        try {
          const response = await axios.get('/api/status');
          backgroundTaskStatus.value = response.data;
        } catch (error) {}
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

onBeforeUnmount(() => { if (statusIntervalId) clearInterval(statusIntervalId); });
</script>

<style scoped>
.loader-container { position: absolute; top: 0; left: 0; z-index: 9999; background: transparent; backdrop-filter: blur(20px); }
</style>