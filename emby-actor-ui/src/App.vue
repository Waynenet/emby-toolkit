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
/* ==================== 1. 动态主题变量 ==================== */
:root {
  /* 白天模式：山水风景 */
  --global-bg-image: url('https://images.unsplash.com/photo-1464822759023-fed622ff2c3b?q=80&w=2564&auto=format&fit=crop'); 
  --global-bg-color: #4a6b82;
  --glass-bg: rgba(255, 255, 255, 0.1); 
  --glass-bg-hover: rgba(255, 255, 255, 0.2);
  --glass-border: rgba(255, 255, 255, 0.2); 
  --glass-border-light: rgba(255, 255, 255, 0.4);
  --glass-shadow: 0 4px 16px 0 rgba(0, 0, 0, 0.1); 
  --glass-blur: blur(12px); 
  --text-primary: rgba(255, 255, 255, 0.95); 
  --text-secondary: rgba(255, 255, 255, 0.75);
  
  /* 多彩模块基色 (白天模式更亮) */
  --tint-blue: linear-gradient(135deg, rgba(255,255,255,0.1) 0%, rgba(112,192,232,0.15) 100%);
  --tint-green: linear-gradient(135deg, rgba(255,255,255,0.1) 0%, rgba(99,226,183,0.15) 100%);
  --tint-purple: linear-gradient(135deg, rgba(255,255,255,0.1) 0%, rgba(138,43,226,0.15) 100%);
  --tint-orange: linear-gradient(135deg, rgba(255,255,255,0.1) 0%, rgba(242,201,125,0.15) 100%);
  --tint-red: linear-gradient(135deg, rgba(255,255,255,0.1) 0%, rgba(232,128,128,0.15) 100%);
}

html.dark {
  /* 黑夜模式：灰黑极简 */
  --global-bg-image: url('https://images.unsplash.com/photo-1550684848-fac1c5b4e853?q=80&w=2564&auto=format&fit=crop'); 
  --global-bg-color: #121212;
  --glass-bg: rgba(20, 25, 35, 0.15); 
  --glass-bg-hover: rgba(30, 35, 45, 0.25);
  --glass-border: rgba(255, 255, 255, 0.05); 
  --glass-border-light: rgba(255, 255, 255, 0.15);
  --glass-shadow: 0 4px 16px 0 rgba(0, 0, 0, 0.3);
  --glass-blur: blur(0px); 
  --text-primary: rgba(255, 255, 255, 0.95);
  --text-secondary: rgba(255, 255, 255, 0.65);
  
  /* 多彩模块基色 (黑夜模式更深) */
  --tint-blue: linear-gradient(135deg, rgba(20,25,35,0.15) 0%, rgba(112,192,232,0.08) 100%);
  --tint-green: linear-gradient(135deg, rgba(20,25,35,0.15) 0%, rgba(99,226,183,0.08) 100%);
  --tint-purple: linear-gradient(135deg, rgba(20,25,35,0.15) 0%, rgba(138,43,226,0.08) 100%);
  --tint-orange: linear-gradient(135deg, rgba(20,25,35,0.15) 0%, rgba(242,201,125,0.08) 100%);
  --tint-red: linear-gradient(135deg, rgba(20,25,35,0.15) 0%, rgba(232,128,128,0.08) 100%);
}

html, body { 
  height: 100vh; 
  margin: 0; 
  padding: 0; 
  font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "Helvetica Neue", Arial, sans-serif; 
  overflow: hidden; 
  background-color: var(--global-bg-color);
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
  transition: background 0.3s, border-color 0.3s, transform 0.2s, box-shadow 0.2s !important;
  height: 100%;
  display: flex !important;
  flex-direction: column !important;
  font-size: 14px; 
}

/* 多彩模块辅助类 */
.n-card.dashboard-card.tint-blue { background: var(--tint-blue) !important; }
.n-card.dashboard-card.tint-green { background: var(--tint-green) !important; }
.n-card.dashboard-card.tint-purple { background: var(--tint-purple) !important; }
.n-card.dashboard-card.tint-orange { background: var(--tint-orange) !important; }
.n-card.dashboard-card.tint-red { background: var(--tint-red) !important; }

.n-card.dashboard-card:hover {
  border-color: var(--glass-border-light) !important;
  transform: translateY(-2px) !important;
  box-shadow: 0 8px 24px 0 rgba(0, 0, 0, 0.2) !important;
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

/* ==================== 3. 彻底隐藏滚动条 ==================== */
* { scrollbar-width: none !important; -ms-overflow-style: none !important; }
::-webkit-scrollbar { display: none !important; width: 0 !important; height: 0 !important; }
.n-scrollbar-rail { display: none !important; }
</style>