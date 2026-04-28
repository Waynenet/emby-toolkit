<!-- src/App.vue -->
<template>
  <!-- ★ 把 canvas 用 Teleport 直接挂到 body，脱离 #app 的层叠上下文 -->
  <Teleport to="body">
    <canvas
      v-if="isDarkTheme"
      id="starfield"
    />
  </Teleport>

  <n-config-provider :theme="isDarkTheme ? darkTheme : undefined" :theme-overrides="currentNaiveTheme" :locale="zhCN" :date-locale="dateZhCN">
    <n-message-provider placement="bottom-right">
      <n-dialog-provider>
        <AppContent />
      </n-dialog-provider>
    </n-message-provider>
  </n-config-provider>
</template>

<script setup>
import { ref, watch, onMounted, onUnmounted, nextTick } from 'vue';
import { NConfigProvider, NMessageProvider, NDialogProvider, darkTheme, zhCN, dateZhCN } from 'naive-ui';
import AppContent from './AppContent.vue';

const isDarkTheme = ref(localStorage.getItem('isDark') === 'true');

// ========== 1. 终极优化：全局底层主题覆盖 ==========
// 通过 JS 层接管 Naive UI 的默认颜色，防止底层组件渲染出白色背景或灰色字体
const baseThemeOverrides = {
  common: {
    textColor1: 'rgba(255, 255, 255, 0.95)',
    textColor2: 'rgba(255, 255, 255, 0.85)',
    textColor3: 'rgba(255, 255, 255, 0.65)',
    textColorDisabled: 'rgba(255, 255, 255, 0.4)',
    placeholderColor: 'rgba(255, 255, 255, 0.5)',
    placeholderColorDisabled: 'rgba(255, 255, 255, 0.3)',
    iconColor: 'rgba(255, 255, 255, 0.9)',
    popoverColor: 'transparent', // 让浮层默认透明，交给 CSS 毛玻璃处理
    modalColor: 'transparent',
    cardColor: 'transparent',
    bodyColor: 'transparent'
  }
};

// 初始化当前主题，默认合并我们的基础毛玻璃主题
const currentNaiveTheme = ref({ ...baseThemeOverrides });

// ========== 星空逻辑 ==========
let animFrameId = null; // 用于取消 requestAnimationFrame

function setupStarfield() {
  const canvas = document.getElementById('starfield');
  if (!canvas) return;

  const ctx = canvas.getContext('2d');
  let width, height, starsArr, initialBurst = true;

  const STAR_COUNT = () => Math.floor(0.3 * width);
  const COLORS = { giant: '180,184,240', star: '226,225,142', comet: '225,225,225' };

  function randomChance(p) { return Math.random() * 1000 < p * 10; }
  function randomRange(min, max) { return Math.random() * (max - min) + min; }

  class Star {
    constructor() { this.reset(); }
    reset() {
      this.isGiant = randomChance(3);
      this.isComet = !this.isGiant && !initialBurst && randomChance(20);
      this.x = randomRange(0, width); this.y = randomRange(0, height);
      this.size = randomRange(1.1, 2.6);
      this.dx = randomRange(0.05, 0.3) + (this.isComet ? randomRange(2.5, 6) : 0.05);
      this.dy = -randomRange(0.05, 0.3) - (this.isComet ? randomRange(2.5, 6) : 0.05);
      this.opacity = 0; this.opacityTarget = randomRange(0.2, this.isComet ? 0.6 : 1);
      this.fadeSpeed = randomRange(0.0005, 0.002) + (this.isComet ? 0.001 : 0);
      this.fadingIn = true; this.fadingOut = false;
    }
    fadeIn() { if (this.fadingIn) { this.opacity += this.fadeSpeed; if (this.opacity >= this.opacityTarget) this.fadingIn = false; } }
    fadeOut() { if (this.fadingOut) { this.opacity -= this.fadeSpeed / 2; if (this.opacity <= 0) this.reset(); } }
    move() { this.x += this.dx; this.y += this.dy; if (!this.fadingOut && (this.x > width - width / 4 || this.y < 0)) this.fadingOut = true; }
    draw() {
      ctx.beginPath();
      if (this.isGiant) {
        ctx.fillStyle = `rgba(${COLORS.giant},${this.opacity})`;
        ctx.arc(this.x, this.y, 2, 0, 2 * Math.PI);
      } else if (this.isComet) {
        ctx.fillStyle = `rgba(${COLORS.comet},${this.opacity})`;
        ctx.arc(this.x, this.y, 2, 0, 2 * Math.PI);
        for (let i = 0; i < 30; i++) {
          const trailOpacity = this.opacity - (this.opacity / 20 * i);
          if (trailOpacity <= 0) break;
          ctx.fillStyle = `rgba(${COLORS.comet},${trailOpacity})`;
          ctx.rect(this.x - this.dx / 4 * i, this.y - this.dy / 4 * i - 2, 2, 2);
          ctx.fill();
        }
        return;
      } else {
        ctx.fillStyle = `rgba(${COLORS.star},${this.opacity})`;
        ctx.fillRect(this.x, this.y, this.size, this.size);
      }
      ctx.closePath(); ctx.fill();
    }
  }

  function resizeCanvas() {
    width = window.innerWidth; height = window.innerHeight;
    canvas.width = width; canvas.height = height;
  }

  function update() {
    ctx.clearRect(0, 0, width, height);
    ctx.globalCompositeOperation = 'lighter';
    for (let s of starsArr) { s.move(); s.fadeIn(); s.fadeOut(); s.draw(); }
    animFrameId = requestAnimationFrame(update);
  }

  function init() {
    resizeCanvas();
    starsArr = Array.from({ length: STAR_COUNT() }, () => new Star());
    update();
    setTimeout(() => initialBurst = false, 50);
  }

  window.addEventListener('resize', resizeCanvas);
  init();
}

function destroyStarfield() {
  if (animFrameId) {
    cancelAnimationFrame(animFrameId);
    animFrameId = null;
  }
}

// ========== 监听暗色模式，动态启停星空 ==========
watch(isDarkTheme, async (val) => {
  if (val) {
    await nextTick();
    setupStarfield();
  } else {
    destroyStarfield();
  }
}, { immediate: false });

// ========== 生命周期 ==========
onMounted(() => {
  const app = document.getElementById('app');

  app.addEventListener('update-naive-theme', (event) => {
    // 深度合并外部传入的主题与我们的基础主题
    currentNaiveTheme.value = {
      ...baseThemeOverrides,
      ...event.detail,
      common: {
        ...baseThemeOverrides.common,
        ...(event.detail?.common || {})
      }
    };
  });

  app.addEventListener('update-dark-mode', (event) => {
    isDarkTheme.value = event.detail;
  });

  if (isDarkTheme.value) {
    setupStarfield();
  }
});

onUnmounted(() => {
  destroyStarfield();
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
  --global-bg-image: none;
  --global-bg-color: #090a14;
  --glass-bg: rgba(20, 25, 35, 0.15); 
  --glass-bg-hover: rgba(30, 35, 45, 0.25);
  --glass-border: rgba(255, 255, 255, 0.05); 
  --glass-border-light: rgba(255, 255, 255, 0.15);
  --glass-shadow: 0 4px 16px 0 rgba(0, 0, 0, 0.3);
  --glass-blur: blur(0px); 
  --text-primary: rgba(255, 255, 255, 0.95);
  --text-secondary: rgba(255, 255, 255, 0.65);
  
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

/* ★ 终极兜底：强制接管 Naive UI 基础文字 CSS 变量，确保无遗漏灰色字 */
:root, [class^="n-"] {
  --n-text-color: rgba(255, 255, 255, 0.95) !important;
  --n-text-color-hover: #ffffff !important;
  --n-text-color-pressed: rgba(255, 255, 255, 0.8) !important;
  --n-text-color-focus: #ffffff !important;
  --n-text-color-disabled: rgba(255, 255, 255, 0.4) !important;
  --n-title-text-color: #ffffff !important;
  --n-icon-color: rgba(255, 255, 255, 0.9) !important;
  --n-placeholder-color: rgba(255, 255, 255, 0.5) !important;
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

/* 背景遮罩 */
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

#starfield {
  position: fixed;
  top: 0;
  left: 0;
  width: 100%;
  height: 100%;
  z-index: 0;
  pointer-events: none;
  display: block;
}

.fullscreen-container { 
  display: flex; justify-content: center; align-items: center; 
  height: 100vh; width: 100%; background: transparent; 
}

/* ==================== 弹窗内所有 n-card 毛玻璃化 ==================== */
.n-card {
  background: var(--glass-bg) !important;
  backdrop-filter: var(--glass-blur) !important;
  -webkit-backdrop-filter: var(--glass-blur) !important;
  border: 1px solid var(--glass-border) !important;
  color: var(--text-primary) !important;
}

.n-card-header,
.n-card__content,
.n-card__footer,
.n-card-header__main {
  background: transparent !important;
  color: var(--text-primary) !important;
}

.n-card[embedded],
.n-card--embedded {
  background: rgba(255, 255, 255, 0.05) !important;
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

.n-card.dashboard-card.no-hover:hover {
  transform: none !important;
  box-shadow: var(--glass-shadow) !important;
  background: var(--glass-bg) !important;
  border-color: var(--glass-border) !important;
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

/* ==================== 4. 表单与交互组件毛玻璃化 ==================== */

/* 1. 覆盖 Input, Select 等输入框 */
.n-input, 
.n-base-selection {
  background-color: var(--glass-bg) !important;
  border: 1px solid var(--glass-border) !important;
  border-radius: 4px !important;
  color: #ffffff !important;
  /* ★ 修复紫色闪烁：严禁使用 transition: all，改为只针对背景和边框做动画 */
  transition: background-color 0.3s ease, border-color 0.3s ease, box-shadow 0.3s ease, color 0.3s ease !important;
}

.n-input:hover, .n-input--focus,
.n-base-selection:hover, .n-base-selection--active {
  background-color: var(--glass-bg-hover) !important;
  border-color: var(--glass-border-light) !important;
}

/* 透明化内部的 label 和 tags 容器 */
.n-base-selection-label,
.n-base-selection-tags {
  background-color: transparent !important;
}

/* 移除原生状态边框层 */
.n-base-selection__border,
.n-base-selection__state-border,
.n-input__border,
.n-input__state-border,
.n-radio-button__state-border {
  display: none !important; 
}

/* 输入框内文字颜色 */
.n-input__input-el, 
.n-input__placeholder,
.n-base-selection-input__content,
.n-base-selection-placeholder {
  color: rgba(255, 255, 255, 0.7) !important;
}

/* 2. 覆盖 Radio Button */
.n-radio-button {
  background-color: var(--glass-bg) !important;
  color: rgba(255, 255, 255, 0.7) !important;
  border: 1px solid var(--glass-border) !important;
  border-left: none !important; 
  box-shadow: none !important;
  transition: background-color 0.3s ease, color 0.3s ease !important; /* 修复紫色闪烁 */
}
.n-radio-button:first-child {
  border-left: 1px solid var(--glass-border) !important;
  border-top-left-radius: 4px !important;
  border-bottom-left-radius: 4px !important;
}
.n-radio-button:last-child {
  border-top-right-radius: 4px !important;
  border-bottom-right-radius: 4px !important;
}
.n-radio-button:hover {
  background-color: var(--glass-bg-hover) !important;
  color: #ffffff !important;
}
.n-radio-button.n-radio-button--checked {
  background-color: #18a058 !important; 
  color: #ffffff !important;
  font-weight: bold !important;
  border-color: #18a058 !important;
  box-shadow: none !important; 
}

/* 3. 覆盖普通按钮 */
.n-button--default-type {
  background: var(--glass-bg) !important;
  border: 1px solid var(--glass-border) !important;
  color: #ffffff !important;
}
.n-button--default-type:hover {
  background: var(--glass-bg-hover) !important;
  border-color: var(--glass-border-light) !important;
}

/* 4. 覆盖 Tag 标签 */
.n-tag {
  background: rgba(255, 255, 255, 0.15) !important;
  border: 1px solid var(--glass-border) !important;
  color: #ffffff !important;
}
.n-tag__close:hover {
  color: #ff4d4f !important;
}

/* ==================== 5. 弹窗/浮层彻底毛玻璃化 ==================== */

/* ★ 补全了所有可能会在顶层弹出的组件（弹窗、日历、提示、抽屉等） */
.n-popover,
.n-dropdown-menu,
.n-base-select-menu,
.n-dialog,
.n-modal,
.n-drawer,
.n-date-panel,
.n-time-picker-panel,
.n-tooltip,
.n-popconfirm__panel {
  background: var(--glass-bg) !important;
  backdrop-filter: var(--glass-blur) !important;
  -webkit-backdrop-filter: var(--glass-blur) !important;
  border: 1px solid var(--glass-border) !important;
  box-shadow: var(--glass-shadow) !important;
  border-radius: 8px !important;
}

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

/* 文字增加一点阴影防白底看不清 */
body {
  text-shadow: 0 1px 2px rgba(0, 0, 0, 0.3);
}

/* ==================== 6. n-alert / n-table 毛玻璃化 ==================== */

.n-alert {
  background-color: var(--glass-bg) !important;
  backdrop-filter: var(--glass-blur) !important;
  -webkit-backdrop-filter: var(--glass-blur) !important;
  border: 1px solid var(--glass-border) !important;
  border-radius: 8px !important;
  box-shadow: var(--glass-shadow) !important;
}

.n-alert.n-alert--info-type    { border-left: 4px solid #2080f0 !important; }
.n-alert.n-alert--success-type { border-left: 4px solid #18a058 !important; }
.n-alert.n-alert--warning-type { border-left: 4px solid #f0a020 !important; }
.n-alert.n-alert--error-type   { border-left: 4px solid #d03050 !important; }

.n-alert .n-alert-body__title,
.n-alert .n-alert-body__content,
.n-alert .n-alert-body,
.n-alert li {
  color: var(--text-primary) !important;
}

.n-alert .n-base-icon { opacity: 0.9; }

.n-text {
  color: var(--text-primary) !important;
}

.n-table {
  background: transparent !important;
}

.n-table th {
  background: rgba(255, 255, 255, 0.08) !important;
  color: var(--text-primary) !important;
  border-color: var(--glass-border) !important;
}

.n-table td {
  background: transparent !important;
  color: var(--text-primary) !important;
  border-color: var(--glass-border) !important;
}

.n-table tr:hover td {
  background: var(--glass-bg-hover) !important;
}
</style>