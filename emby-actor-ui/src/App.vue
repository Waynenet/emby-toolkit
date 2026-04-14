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
    
    // 1. 监听来自 AppContent 的主题更新事件 (Naive UI 样式)
    app.addEventListener('update-naive-theme', (event) => {
        currentNaiveTheme.value = event.detail;
    });

    // 2. 监听来自 AppContent 的暗色模式切换事件
    app.addEventListener('update-dark-mode', (event) => {
        isDarkTheme.value = event.detail;
    });
});
</script>

<style>
/* ==================== 全局静态样式与基础布局 ==================== */
html, body { 
  height: 100vh; 
  margin: 0; 
  padding: 0; 
  font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "Helvetica Neue", Arial, sans-serif; 
  overflow: hidden; 
  
  /* ★ 使用 CSS 变量接管全局渐变背景 ★ */
  /* 如果变量还未注入，逗号后面的代码作为默认的容错兜底背景 */
  background: var(--global-bg, linear-gradient(135deg, #f5f7fa 0%, #e3eeff 100%)); 
  background-attachment: fixed;
  transition: background 0.5s ease;
}

/* 确保登录页等纯内容容器透明，自然透出 body 的柔和渐变背景 */
.fullscreen-container { 
  display: flex; 
  justify-content: center; 
  align-items: center; 
  height: 100vh; 
  width: 100%; 
  background: transparent; 
}
</style>