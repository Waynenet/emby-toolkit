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
/* ==================== 1. 全局静态基础布局 & 壁纸 ==================== */
:root {
  /* 核心壁纸：你可以换成你喜欢的任意高清图片URL */
  --global-bg-image: url('https://images.unsplash.com/photo-1618005182384-a83a8bd57fbe?q=80&w=2564&auto=format&fit=crop');
  
  /* 毛玻璃核心参数 */
  --glass-bg: rgba(20, 25, 35, 0.45); 
  --glass-bg-hover: rgba(30, 35, 45, 0.55);
  --glass-border: rgba(255, 255, 255, 0.12); 
  --glass-border-light: rgba(255, 255, 255, 0.25);
  --glass-shadow: 0 8px 32px 0 rgba(0, 0, 0, 0.3);
  --glass-blur: blur(24px); 
  
  /* 文字颜色 */
  --text-primary: rgba(255, 255, 255, 0.95);
  --text-secondary: rgba(255, 255, 255, 0.65);
}

html, body { 
  height: 100vh; 
  margin: 0; 
  padding: 0; 
  font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "Helvetica Neue", Arial, sans-serif; 
  overflow: hidden; 
  
  /* 使用全屏背景图 */
  background-image: var(--global-bg-image);
  background-size: cover;
  background-position: center;
  background-attachment: fixed;
  color: var(--text-primary);
}

.fullscreen-container { 
  display: flex; 
  justify-content: center; 
  align-items: center; 
  height: 100vh; 
  width: 100%; 
  background: transparent; 
}

/* ==================== 2. 全局卡片 (高级毛玻璃拟态) 样式 ==================== */
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
  box-shadow: 0 12px 40px 0 rgba(0, 0, 0, 0.4) !important;
}

.dashboard-card > .n-card__content {
  flex-grow: 1 !important;
  display: flex !important;
  flex-direction: column !important;
  justify-content: space-between !important;
}

.dashboard-card .n-card-header {
  border-bottom: 1px solid rgba(255, 255, 255, 0.05) !important;
  padding-bottom: 12px !important;
}

.dashboard-card .card-title {
  color: var(--text-primary) !important; 
  font-weight: 600 !important;
  font-size: 1.1rem;
  letter-spacing: 0.5px;
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
  background: rgba(30, 35, 45, 0.85) !important;
  backdrop-filter: blur(24px) !important;
  -webkit-backdrop-filter: blur(24px) !important;
  border: 1px solid var(--glass-border) !important;
  border-radius: 16px !important;
  box-shadow: 0 12px 32px rgba(0, 0, 0, 0.4) !important;
  color: #fff !important;
}

/* ==================== 4. 瀑布流入场动画 ==================== */
@keyframes card-fade-in { to { opacity: 1; transform: translateY(0); } }
.dashboard-card:nth-child(1) { animation-delay: 0.05s; }
.dashboard-card:nth-child(2) { animation-delay: 0.10s; }
.dashboard-card:nth-child(3) { animation-delay: 0.15s; }
.dashboard-card:nth-child(4) { animation-delay: 0.20s; }
.dashboard-card:nth-child(5) { animation-delay: 0.25s; }

/* ==================== 5. 全局滚动条隐藏 (保留滚动功能) ==================== */
* {
  scrollbar-width: none; 
  -ms-overflow-style: none; 
}
::-webkit-scrollbar {
  display: none; 
  width: 0;      
  height: 0;     
}
</style>