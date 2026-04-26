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
  --global-bg-image: url('https://60s.748541.xyz/v2/bing?encoding=image'); 
  --global-bg-color: #4a6b82;
  --glass-bg: rgba(255, 255, 255, 0.1); 
  --glass-bg-hover: rgba(255, 255, 255, 0.2);
  --glass-border: rgba(255, 255, 255, 0.2); 
  --glass-border-light: rgba(255, 255, 255, 0.4);
  --glass-shadow: 0 4px 16px 0 rgba(0, 0, 0, 0.1); 
  --glass-blur: blur(12px); 
  --text-primary: rgba(255, 255, 255, 0.95); 
  --text-secondary: rgba(255, 255, 255, 0.75);
  
  /* 多彩模块基色 (白天模式) */
  --overlay-color: rgba(0, 0, 0, 0.4);

  --tint-blue: linear-gradient(135deg, rgba(255,255,255,0.1) 0%, rgba(54, 162, 235, 0.45) 100%);
  --tint-blue-hover: linear-gradient(135deg, rgba(255,255,255,0.2) 0%, rgba(54, 162, 235, 0.55) 100%);
  
  --tint-green: linear-gradient(135deg, rgba(255,255,255,0.1) 0%, rgba(75, 192, 192, 0.45) 100%);
  --tint-green-hover: linear-gradient(135deg, rgba(255,255,255,0.2) 0%, rgba(75, 192, 192, 0.55) 100%);
  
  --tint-purple: linear-gradient(135deg, rgba(255,255,255,0.1) 0%, rgba(153, 102, 255, 0.45) 100%);
  --tint-purple-hover: linear-gradient(135deg, rgba(255,255,255,0.2) 0%, rgba(153, 102, 255, 0.55) 100%);
  
  --tint-orange: linear-gradient(135deg, rgba(255,255,255,0.1) 0%, rgba(255, 159, 64, 0.45) 100%);
  --tint-orange-hover: linear-gradient(135deg, rgba(255,255,255,0.2) 0%, rgba(255, 159, 64, 0.55) 100%);
  
  --tint-red: linear-gradient(135deg, rgba(255,255,255,0.1) 0%, rgba(255, 99, 132, 0.45) 100%);
  --tint-red-hover: linear-gradient(135deg, rgba(255,255,255,0.2) 0%, rgba(255, 99, 132, 0.55) 100%);
}

html.dark {
  /* 黑夜模式：真正的灰黑极简暗纹 */
  --global-bg-image: url('https://images.unsplash.com/photo-1614850523459-c2f4c699c52e?q=80&w=2564&auto=format&fit=crop'); 
  --global-bg-color: #121212;
  --glass-bg: rgba(20, 25, 35, 0.15); 
  --glass-bg-hover: rgba(30, 35, 45, 0.25);
  --glass-border: rgba(255, 255, 255, 0.05); 
  --glass-border-light: rgba(255, 255, 255, 0.15);
  --glass-shadow: 0 4px 16px 0 rgba(0, 0, 0, 0.3);
  --glass-blur: blur(0px); 
  --text-primary: rgba(255, 255, 255, 0.95);
  --text-secondary: rgba(255, 255, 255, 0.65);
  
  /* 多彩模块基色 (黑夜模式) */
  --overlay-color: transparent;

  --tint-blue: linear-gradient(135deg, rgba(20,25,35,0.15) 0%, rgba(112,192,232,0.08) 100%);
  --tint-blue-hover: linear-gradient(135deg, rgba(30,35,45,0.3) 0%, rgba(54, 162, 235, 0.45) 100%);
  
  --tint-green: linear-gradient(135deg, rgba(20,25,35,0.15) 0%, rgba(99,226,183,0.08) 100%);
  --tint-green-hover: linear-gradient(135deg, rgba(30,35,45,0.3) 0%, rgba(75, 192, 192, 0.45) 100%);
  
  --tint-purple: linear-gradient(135deg, rgba(20,25,35,0.15) 0%, rgba(138,43,226,0.08) 100%);
  --tint-purple-hover: linear-gradient(135deg, rgba(30,35,45,0.3) 0%, rgba(153, 102, 255, 0.45) 100%);
  
  --tint-orange: linear-gradient(135deg, rgba(20,25,35,0.15) 0%, rgba(242,201,125,0.08) 100%);
  --tint-orange-hover: linear-gradient(135deg, rgba(30,35,45,0.3) 0%, rgba(255, 159, 64, 0.45) 100%);
  
  --tint-red: linear-gradient(135deg, rgba(20,25,35,0.15) 0%, rgba(232,128,128,0.08) 100%);
  --tint-red-hover: linear-gradient(135deg, rgba(30,35,45,0.3) 0%, rgba(255, 99, 132, 0.45) 100%);
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

/* 背景遮罩：白天半透明黑色，黑夜透明 */
body::before {
  content: '';
  position: fixed;
  inset: 0;
  background: var(--overlay-color);
  pointer-events: none;
  z-index: 0;
  transition: background 0.3s ease;
}

#app {
  position: relative;
  z-index: 1;
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
  transition: transform 0.2s, box-shadow 0.2s !important;
  height: 100%;
  display: flex !important;
  flex-direction: column !important;
  font-size: 14px; 
}

.n-card.dashboard-card:hover {
  background: var(--glass-bg-hover) !important;
  border-color: var(--glass-border-light) !important;
  transform: translateY(-2px) !important;
  box-shadow: 0 8px 24px 0 rgba(0, 0, 0, 0.2) !important;
}

.n-card.dashboard-card.tint-blue { background: var(--tint-blue) !important; }
.n-card.dashboard-card.tint-blue:hover { background: var(--tint-blue-hover) !important; }
.n-card.dashboard-card.tint-green { background: var(--tint-green) !important; }
.n-card.dashboard-card.tint-green:hover { background: var(--tint-green-hover) !important; }
.n-card.dashboard-card.tint-purple { background: var(--tint-purple) !important; }
.n-card.dashboard-card.tint-purple:hover { background: var(--tint-purple-hover) !important; }
.n-card.dashboard-card.tint-orange { background: var(--tint-orange) !important; }
.n-card.dashboard-card.tint-orange:hover { background: var(--tint-orange-hover) !important; }
.n-card.dashboard-card.tint-red { background: var(--tint-red) !important; }
.n-card.dashboard-card.tint-red:hover { background: var(--tint-red-hover) !important; }

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

/* ==================== 4. 表单与交互组件毛玻璃化 (全局覆盖) ==================== */

/* 1. 覆盖 Input, Select, InputNumber 等输入框 */
.n-input, 
.n-base-selection {
  background-color: var(--glass-bg) !important;
  border: 1px solid var(--glass-border) !important;
  border-radius: 4px !important;
  color: #ffffff !important;
  transition: all 0.3s ease !important;
}
.n-input:hover, .n-input--focus,
.n-base-selection:hover, .n-base-selection--active {
  background-color: var(--glass-bg-hover) !important;
  border-color: var(--glass-border-light) !important;
}

/* 修复 Select 下拉框原框是白色的问题：透明化内部的 label 和 tags 容器 */
.n-base-selection-label,
.n-base-selection-tags {
  background-color: transparent !important;
}

/* 彻底移除 Naive UI 原生的状态边框层（这就是各种奇怪绿线和白底的罪魁祸首） */
.n-base-selection__border,
.n-base-selection__state-border,
.n-input__border,
.n-input__state-border,
.n-radio-button__state-border {
  display: none !important; 
}

/* 输入框内的文字颜色 */
.n-input__input-el, 
.n-input__placeholder,
.n-base-selection-input__content,
.n-base-selection-placeholder {
  color: rgba(255, 255, 255, 0.9) !important;
}

/* 2. 覆盖 Radio Button (解决绿线问题，选中状态改为全局主色绿) */
.n-radio-group .n-radio-button {
  background-color: var(--glass-bg) !important;
  color: rgba(255, 255, 255, 0.7) !important;
  border: 1px solid var(--glass-border) !important;
  border-left: none !important; /* 去除中间的多重边框 */
  box-shadow: none !important;
}
/* 给第一个按钮补回左边框和圆角 */
.n-radio-group .n-radio-button:first-child {
  border-left: 1px solid var(--glass-border) !important;
  border-top-left-radius: 4px !important;
  border-bottom-left-radius: 4px !important;
}
/* 给最后一个按钮修复圆角 */
.n-radio-group .n-radio-button:last-child {
  border-top-right-radius: 4px !important;
  border-bottom-right-radius: 4px !important;
}
.n-radio-group .n-radio-button:hover {
  background-color: var(--glass-bg-hover) !important;
  color: #ffffff !important;
}

/* 选中状态：变成类似 Primary 按钮的纯绿色填充 */
.n-radio-group .n-radio-button.n-radio-button--checked {
  background-color: #18a058 !important; /* Naive UI 默认的主色绿 */
  color: #ffffff !important;
  font-weight: bold !important;
  border-color: #18a058 !important;
  box-shadow: none !important; 
}

/* 3. 覆盖普通按钮 (如：排序按钮) */
.n-button--default-type {
  background: var(--glass-bg) !important;
  border: 1px solid var(--glass-border) !important;
  color: #ffffff !important;
}
.n-button--default-type:hover {
  background: var(--glass-bg-hover) !important;
  border-color: var(--glass-border-light) !important;
}

/* 4. 覆盖 Tag 标签 (如选择多个类型时的已选标签) */
.n-tag {
  background: rgba(255, 255, 255, 0.15) !important;
  border: 1px solid var(--glass-border) !important;
  color: #ffffff !important;
}
.n-tag__close:hover {
  color: #ff4d4f !important;
}

/* ==================== 5. 解决纯白背景与黑灰字体问题 ==================== */

/* 解决下拉框变纯白的问题：Naive UI 的下拉框是包在 popover 里的 */
.n-popover,
.n-dropdown-menu,
.n-base-select-menu {
  background: var(--glass-bg) !important;
  backdrop-filter: var(--glass-blur) !important;
  -webkit-backdrop-filter: var(--glass-blur) !important;
  border: 1px solid var(--glass-border) !important;
  box-shadow: var(--glass-shadow) !important;
  border-radius: 8px !important;
}
/* 下拉菜单的选项文字与 Hover 状态 */
.n-base-select-option, 
.n-dropdown-option {
  color: rgba(255, 255, 255, 0.9) !important;
}
.n-base-select-option:hover, 
.n-base-select-option--pending,
.n-base-select-option--selected {
  background: rgba(255, 255, 255, 0.2) !important;
  color: #ffffff !important;
}

/* 暴力接管全局字体颜色：无论日夜模式，强制所有常见文本元素为白色 */
body,
.n-page-header__title,
.n-page-header__subtitle,
.n-thing-main__header,
.n-thing-main__description,
.n-form-item-label,
.n-checkbox__label,
.n-radio__label,
.n-statistic-value__content,
.n-statistic__label,
.n-empty__description,
.n-divider__title,
.filter-label {
  color: #ffffff !important;
  text-shadow: 0 1px 2px rgba(0, 0, 0, 0.3); /* 增加一点文字阴影，防止在纯白背景图上看不清 */
}

/* 弱化次要文本的颜色（如：副标题、时间等） */
.n-page-header__subtitle,
.n-empty__description {
  color: rgba(255, 255, 255, 0.7) !important;
}
</style>