<!-- src/App.vue -->
<template>
  <n-config-provider :theme="isDarkTheme ? darkTheme : undefined" :theme-overrides="currentNaiveTheme" :locale="zhCN" :date-locale="dateZhCN">
    <n-message-provider placement="bottom-right">
      <n-dialog-provider>
        <AppContent />
      </n-dialog-provider>
    </n-message-provider>
  </n-config-provider>
</template>

<script setup>
import { ref, onMounted } from 'vue';
import { NConfigProvider, NMessageProvider, NDialogProvider, darkTheme, zhCN, dateZhCN } from 'naive-ui';
import AppContent from './AppContent.vue';

const isDarkTheme = ref(localStorage.getItem('isDark') === 'true');
const currentNaiveTheme = ref({});

onMounted(() => {
    const app = document.getElementById('app');
    
    app.addEventListener('update-naive-theme', (event) => {
        currentNaiveTheme.value = event.detail;
    });

    app.addEventListener('update-dark-mode', (event) => {
        isDarkTheme.value = event.detail;
    });
});
</script>

<style>
/* ==================== 1. 动态主题变量 (修复白天模式通透感) ==================== */
:root {
  /* 默认(白天)变量 - 增加通透感 */
  --global-bg-image: url('https://images.unsplash.com/photo-1507525428034-b723cf961d3e?q=80&w=2564&auto=format&fit=crop');
  --glass-bg: rgba(255, 255, 255, 0.25); /* 降低不透明度，更通透 */
  --glass-bg-hover: rgba(255, 255, 255, 0.4);
  --glass-border: rgba(255, 255, 255, 0.4); 
  --glass-border-light: rgba(255, 255, 255, 0.7);
  --glass-shadow: 0 8px 32px 0 rgba(31, 38, 135, 0.1); /* 阴影放轻 */
  --glass-blur: blur(24px); 
  --text-primary: rgba(0, 0, 0, 0.85);
  --text-secondary: rgba(0, 0, 0, 0.6);
}

html.dark {
  /* 暗色模式变量 */
  --global-bg-image: url('https://images.unsplash.com/photo-1618005182384-a83a8bd57fbe?q=80&w=2564&auto=format&fit=crop');
  --glass-bg: rgba(20, 25, 35, 0.45); 
  --glass-bg-hover: rgba(30, 35, 45, 0.6);
  --glass-border: rgba(255, 255, 255, 0.1); 
  --glass-border-light: rgba(255, 255, 255, 0.25);
  --glass-shadow: 0 8px 32px 0 rgba(0, 0, 0, 0.4);
  --text-primary: rgba(255, 255, 255, 0.95);
  --text-secondary: rgba(255, 255, 255, 0.65);
}

html, body { 
  height: 100vh; 
  margin: 0; 
  padding: 0; 
  font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "Helvetica Neue", Arial, sans-serif; 
  overflow: hidden; 
  background-image: var(--global-bg-image);
  background-size: cover;
  background-position: center;
  background-attachment: fixed;
  color: var(--text-primary);
  transition: background-image 0.5s ease, color 0.3s ease;
}

.fullscreen-container { 
  display: flex; justify-content: center; align-items: center; 
  height: 100vh; width: 100%; background: transparent; 
}

/* ==================== 2. 全局卡片 (毛玻璃) ==================== */
.n-card.dashboard-card {
  background: var(--glass-bg) !important;
  backdrop-filter: var(--glass-blur) !important;
  -webkit-backdrop-filter: var(--glass-blur) !important;
  border: 1px solid var(--glass-border) !important;
  box-shadow: var(--glass-shadow) !important;
  color: var(--text-primary) !important;
  border-radius: 16px !important;
  transition: all 0.3s cubic-bezier(0.25, 0.8, 0.25, 1) !important;
  height: 100%;
  display: flex !important;
  flex-direction: column !important;
  opacity: 0;
  font-size: 14px; 
  transform: translateY(20px); 
  animation: card-fade-in 0.5s cubic-bezier(0.25, 0.8, 0.25, 1) forwards;
}

.n-card.dashboard-card:hover {
  background: var(--glass-bg-hover) !important;
  border-color: var(--glass-border-light) !important;
  transform: translateY(-4px) !important;
}

.dashboard-card > .n-card__content {
  flex-grow: 1 !important;
  display: flex !important;
  flex-direction: column !important;
  justify-content: space-between !important;
}

.dashboard-card .n-card-header {
  border-bottom: 1px solid var(--glass-border) !important;
  padding-bottom: 12px !important;
}

.dashboard-card .card-title {
  color: var(--text-primary) !important; 
  font-weight: 600 !important;
  font-size: 1.1rem;
}

.n-card.dashboard-card.series-card { flex-direction: row !important; height: auto !important; }
.n-card.dashboard-card.series-card > .n-card__content { flex-direction: row !important; justify-content: flex-start !important; padding: 12px !important; gap: 16px !important; overflow: hidden; }
.card-poster-container { flex-shrink: 0; width: 120px !important; height: 180px !important; overflow: hidden; border-radius: 8px; box-shadow: 0 4px 12px rgba(0,0,0,0.15); }

.modal-card-lite {
  background: var(--glass-bg) !important;
  backdrop-filter: var(--glass-blur) !important;
  -webkit-backdrop-filter: var(--glass-blur) !important;
  border: 1px solid var(--glass-border) !important;
  border-radius: 16px !important;
  box-shadow: var(--glass-shadow) !important;
  color: var(--text-primary) !important;
}

@keyframes card-fade-in { to { opacity: 1; transform: translateY(0); } }
.dashboard-card:nth-child(1) { animation-delay: 0.05s; }
.dashboard-card:nth-child(2) { animation-delay: 0.10s; }
.dashboard-card:nth-child(3) { animation-delay: 0.15s; }

/* ==================== 3. 彻底隐藏滚动条 ==================== */
* { scrollbar-width: none; -ms-overflow-style: none; }
::-webkit-scrollbar { display: none; width: 0; height: 0; }
</style>