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
    
    // 监听来自 AppContent 的主题更新事件
    app.addEventListener('update-naive-theme', (event) => {
        currentNaiveTheme.value = event.detail;
    });

    // 监听来自 AppContent 的暗色模式切换事件
    app.addEventListener('update-dark-mode', (event) => {
        isDarkTheme.value = event.detail;
    });
});
</script>

<style>
/* ==================== 1. 全局静态基础布局 ==================== */
html, body { 
  height: 100vh; 
  margin: 0; 
  padding: 0; 
  font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "Helvetica Neue", Arial, sans-serif; 
  overflow: hidden; 
  
  /* 使用 CSS 变量接管全局渐变背景 */
  background: var(--global-bg, linear-gradient(135deg, #f5f7fa 0%, #e3eeff 100%)); 
  background-attachment: fixed;
  transition: background 0.5s ease;
}

.fullscreen-container { 
  display: flex; 
  justify-content: center; 
  align-items: center; 
  height: 100vh; 
  width: 100%; 
  background: transparent; 
}

/* ==================== 2. 全局卡片 (玻璃拟态) 样式 ==================== */
.n-card.dashboard-card {
  background: var(--card-bg-color) !important;
  border: 1px solid var(--card-border-color) !important;
  box-shadow: 0 4px 12px var(--card-shadow-color), 0 0 20px -5px var(--accent-glow-color) !important;
  color: var(--text-color) !important;
  border-radius: 12px !important;
  backdrop-filter: blur(16px) !important;
  -webkit-backdrop-filter: blur(16px) !important;
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
  transform: translateY(-5px) !important;
  box-shadow: 0 8px 24px var(--card-shadow-color), 0 0 35px var(--accent-glow-color) !important;
}

.dashboard-card > .n-card__content {
  flex-grow: 1 !important;
  display: flex !important;
  flex-direction: column !important;
  justify-content: space-between !important;
}

.dashboard-card .card-title {
  color: var(--accent-color) !important; 
  font-weight: 600 !important;
  letter-spacing: 0.5px;
  text-shadow: 0 0 12px var(--accent-glow-color);
}

/* 纵向转横向的列表卡片 */
.n-card.dashboard-card.series-card {
  flex-direction: row !important;
  height: auto !important;
}
.n-card.dashboard-card.series-card > .n-card__content {
  flex-direction: row !important;
  justify-content: flex-start !important;
  padding: 12px !important;
  gap: 16px !important;
  overflow: hidden; 
}

/* 海报容器 */
.card-poster-container {
  flex-shrink: 0; 
  width: 120px !important; 
  height: 180px !important;
  overflow: hidden;
  border-radius: 8px;
  box-shadow: 0 4px 12px rgba(0,0,0,0.15); 
}

/* ==================== 3. 模态框 (日志弹窗) 轻量版样式 ==================== */
.modal-card-lite {
  background-color: var(--modal-solid-bg-color) !important;
  border: 1px solid var(--card-border-color) !important;
  border-radius: 12px !important;
  box-shadow: 0 12px 32px rgba(0, 0, 0, 0.25) !important;
  animation: none !important;
  transition: none !important;
}
.modal-card-lite:hover {
  transform: none !important;
}

/* ==================== 4. 瀑布流入场动画 ==================== */
@keyframes card-fade-in { to { opacity: 1; transform: translateY(0); } }
.dashboard-card:nth-child(1) { animation-delay: 0.05s; }
.dashboard-card:nth-child(2) { animation-delay: 0.10s; }
.dashboard-card:nth-child(3) { animation-delay: 0.15s; }
.dashboard-card:nth-child(4) { animation-delay: 0.20s; }
.dashboard-card:nth-child(5) { animation-delay: 0.25s; }
</style>