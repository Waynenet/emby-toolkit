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

/* ★ 终极兜底：强制接管 Naive UI 基础 CSS 变量 */
:root, [class^="n-"] {
  --n-text-color: rgba(255, 255, 255, 0.95) !important;
  --n-text-color-hover: #ffffff !important;
  --n-text-color-pressed: rgba(255, 255, 255, 0.8) !important;
  --n-text-color-focus: #ffffff !important;
  --n-text-color-disabled: rgba(255, 255, 255, 0.4) !important;
  --n-title-text-color: #ffffff !important;
  --n-icon-color: rgba(255, 255, 255, 0.9) !important;
  --n-placeholder-color: rgba(255, 255, 255, 0.5) !important;
  --n-close-icon-color: rgba(255, 255, 255, 0.95) !important;
  --n-close-icon-color-hover: #ffffff !important;
  --n-close-icon-color-pressed: rgba(255, 255, 255, 0.8) !important;
  --n-bar-color: rgba(255, 255, 255, 0.5) !important;
  --n-tab-text-color-active: #ffffff !important;
  --n-tab-text-color-hover: #ffffff !important;
  --n-ripple-color: #18a058 !important;
  --n-border: 1px solid #ffffff00 !important;
  --n-border-hover: 1px solid #ffffff00 !important;
  --n-border-focus: 1px solid #ffffff00 !important;
  --n-border-checked: 1px solid #ffffff00 !important;
  --n-border-disabled: 1px solid #ffffff00 !important;
  --n-box-shadow-active: inset 0 0 0 1px #18a058;
  --n-box-shadow-focus: inset 0 0 0 1px #18a058, 0 0 0 2px rgba(24, 160, 88, 0.2) !important;
  --n-box-shadow-hover: inset 0 0 0 1px #18a058 !important;
  --n-dot-color-active: #18a058 !important;
  --n-button-border-color-active: #18a058 !important;
  --n-button-box-shadow-focus: inset 0 0 0 1px #18a058, 0 0 0 2px rgba(24, 160, 88, 0.3) !important;
  --n-button-text-color-hover: #18a058 !important;
  --n-button-text-color-active: #18a058 !important;
  --n-check-mark-color: #FFF !important;
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
  
  /* 删除会导致漏光的物理 border，改用 inset(内阴影) 完美描边 */
  border: none !important;
  box-shadow: inset 0 0 0 1px var(--glass-border), var(--glass-shadow) !important;
  
  color: var(--text-primary) !important;
  border-radius: 16px !important;
  transition: transform 0.2s, box-shadow 0.2s, background 0.2s !important;
  height: 100%;
  display: flex !important;
  flex-direction: column !important;
  font-size: 14px;

  /* 用 background-clip 限制背景溢出，利用 outline 消除抗锯齿白边 */
  background-clip: padding-box !important;
  outline: 1px solid transparent !important;
}

/* 卡片悬浮状态 */
.n-card.dashboard-card:hover {
  background: var(--glass-bg-hover) !important;
  /* 悬浮时的边框高亮也同步改用 inset box-shadow */
  box-shadow: inset 0 0 0 1px var(--glass-border-light), 0 8px 24px 0 rgba(0, 0, 0, 0.2) !important;
  transform: translateY(-2px) !important;
}

/* 禁用悬浮动画的卡片兜底 */
.n-card.dashboard-card.no-hover:hover {
  transform: none !important;
  box-shadow: inset 0 0 0 1px var(--glass-border), var(--glass-shadow) !important;
  background: var(--glass-bg) !important;
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
.n-button--info-type {
  background: #2080f0 !important;
  border-color: #2080f0 !important;
}
.n-button--info-type:hover {
  background: #2080f0 !important;
  border-color: #2080f0 !important;
}
.n-button--warning-type {
  background: #f0a020 !important;
  border-color: #f0a020 !important;
  color: #ffffff !important;
}
.n-button--warning-type:hover {
  background: #f0a020 !important;
  border-color: #f0a020 !important;
}
.n-button--error-type {
  background: #d03050 !important;
  border-color: #d03050 !important;
  color: #ffffff !important;
}
.n-button--error-type:hover {
  background: #d03050 !important;
  border-color: #d03050 !important;
}
.n-button--transparent-type {
  background: transparent !important;
  border-color: transparent !important;
  color: #ffffff !important;
}
.n-button--transparent-type:hover {
  background: transparent !important;
  border-color: transparent !important;
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

/* ==================== 退出登录/下拉菜单悬浮高亮变绿 (破解伪元素遮挡) ==================== */
/* 必须穿透 ::before 伪元素，才能防止白底盖住绿色 */
.n-dropdown-option-body:hover::before,
.n-dropdown-option-body--pending::before,
.n-base-select-option:hover::before,
.n-base-select-option--pending::before,
.n-menu-popover .n-menu-item-content:hover::before {
  background-color: #18a058 !important; /* 强制覆盖悬浮层为绿色 */
  opacity: 1 !important;
}

/* 确保悬浮时内部的文字和图标变成纯白色，防止看不清 */
.n-dropdown-option-body:hover .n-dropdown-option-body__label,
.n-dropdown-option-body--pending .n-dropdown-option-body__label,
.n-dropdown-option-body:hover .n-dropdown-option-body__icon,
.n-dropdown-option-body--pending .n-dropdown-option-body__icon,
.n-base-select-option:hover,
.n-base-select-option--pending {
  color: #ffffff !important;
}

/* ==================== 侧边栏折叠/展开箭头强制纯白 (破解 div 拼接原理) ==================== */
/* 因为 Naive UI 的 bar 箭头是由两个 div 拼出来的，必须改它们的 background-color */
.n-layout-toggle-bar__top,
.n-layout-toggle-bar__bottom {
  background-color: rgba(255, 255, 255, 0.5) !important;
  box-shadow: 0 0 2px rgba(255,255,255,0.9) !important; /* 增加一点微光防暗 */
}

/* 悬浮时的箭头状态更亮更粗 */
.n-layout-toggle-bar:hover .n-layout-toggle-bar__top,
.n-layout-toggle-bar:hover .n-layout-toggle-bar__bottom {
  background-color: #ffffff !important;
  box-shadow: 0 0 6px rgba(255,255,255,1) !important;
  width: 3px !important; /* 原本可能是 2px，稍微加粗更醒目 */
}

/* 兜底：如果是 button 形态的图标 */
.n-layout-toggle-button .n-base-icon,
.n-layout-toggle-button svg,
.n-layout-toggle-button path {
  color: #ffffff !important;
  fill: #ffffff !important;
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

.n-tag--default-type {
  background: var(--glass-bg) !important;
  border: 1px solid var(--glass-border) !important;
  color: #ffffff !important;
}
.n-tag--info-type {
  background-color: #2080f0 !important;
}
.n-tag--success-type {
  background-color: #18a058 !important;
}
.n-tag--warning--type {
  background-color: #f0a020 !important;
}
.n-tag--error-type {
  background-color: #d03050 !important;
}
.n-tag--cyan-type {
  background-color: #55ff9c !important;
}
.n-tag--closable {
  background: rgba(255, 255, 255, 0.15) !important;
  border: 1px solid var(--glass-border) !important;
  color: #ffffff !important;
}
.n-tag__close:hover {
  color: #ff4d4f !important;
}

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

/* ==================== 7. 高级表格 (n-data-table) 毛玻璃化 ==================== */
/* 强制穿透清除 Naive UI 高级表格自带的各种白底容器 */
.n-data-table,
.n-data-table-wrapper,
.n-data-table-base-table {
  background: transparent !important;
  border-color: var(--glass-border) !important;
}

.n-data-table {
  background: var(--glass-bg) !important;
  backdrop-filter: var(--glass-blur) !important;
  -webkit-backdrop-filter: var(--glass-blur) !important;
  border-radius: 8px !important;
  border: 1px solid var(--glass-border) !important;
  overflow: hidden;
}

.n-data-table .n-data-table-th,
.n-data-table .n-data-table-thead {
  background: rgba(255, 255, 255, 0.08) !important;
  color: var(--text-primary) !important;
  border-bottom: 1px solid var(--glass-border) !important;
  border-color: var(--glass-border) !important;
  font-weight: bold;
}

.n-data-table .n-data-table-td {
  background: transparent !important;
  color: var(--text-primary) !important;
  border-bottom: 1px solid var(--glass-border) !important;
  border-color: var(--glass-border) !important;
}

.n-data-table .n-data-table-tr:hover .n-data-table-td {
  background-color: var(--glass-bg-hover) !important;
}

/* 表头的排序、过滤等功能按钮 */
.n-data-table-th__sort, 
.n-data-table-th__filter {
  color: var(--text-primary) !important;
}
.n-data-table-th__sort:hover, 
.n-data-table-th__filter:hover {
  background: rgba(255, 255, 255, 0.2) !important;
}

/* ==================== 8. 分页器 (Pagination) 毛玻璃化 ==================== */
.n-pagination .n-pagination-item {
  background: var(--glass-bg) !important;
  border: 1px solid var(--glass-border) !important;
  color: var(--text-primary) !important;
  transition: all 0.3s ease;
}

.n-pagination .n-pagination-item:hover {
  background: var(--glass-bg-hover) !important;
  border-color: rgba(255, 255, 255, 0.4) !important;
}

/* 当前选中页码高亮 */
.n-pagination .n-pagination-item--active {
  background: rgba(255, 255, 255, 0.2) !important;
  border-color: rgba(255, 255, 255, 0.5) !important;
  color: #ffffff !important;
  font-weight: bold;
}

/* 如果分页器里有下拉选择框 (比如 10条/页) */
.n-pagination .n-select .n-base-selection {
  background: var(--glass-bg) !important;
  border-color: var(--glass-border) !important;
}

/* ==================== 9. Tabs (标签页) 毛玻璃化 ==================== */
.n-tabs-nav { 
  background-color: transparent !important; 
}
.n-tabs-tab { 
  color: var(--text-secondary) !important; 
}
.n-tabs-tab--active { 
  color: var(--text-primary) !important; 
  font-weight: 600; 
}
.n-tabs-bar,
.n-tabs-rail { 
  background-color: transparent !important; 
}

.n-tabs-capsule {
  background-color: #18a058 !important;
  border-color: #18a058 !important;
}

/* ==================== 10. 终极修复：交互组件变紫/卡色问题 ==================== */

/* 1. 强行覆盖 Naive UI 默认的 transition: all，只对明确的属性做动画，防止浏览器插值计算卡在紫色 */
.n-button,
.n-switch,
.n-radio-button,
.n-checkbox,
.n-input,
.n-base-selection,
.n-tag,
.n-alert {
  transition: background-color 0.3s ease, border-color 0.3s ease, color 0.3s ease, opacity 0.3s ease, box-shadow 0.3s ease !important;
}

/* 2. 彻底禁用按钮点击时产生的波纹 (Ripple) 阴影层，防止产生紫色的幽灵边框 */
.n-base-wave {
  display: none !important;
  animation: none !important;
}
.n-button::after,
.n-radio-button::after {
  box-shadow: none !important;
}

/* 3. 为 Primary (主操作) 按钮兜底，确保无论是日间还是夜间，它的基调始终是绿色系，不会被意外污染 */
.n-button--primary-type {
  background-color: #18a058 !important;
  border-color: #18a058 !important;
  color: #ffffff !important;
}
.n-button--primary-type:hover,
.n-button--primary-type:focus {
  background-color: #36ad6a !important;
  border-color: #36ad6a !important;
}

/* 4. 确保 Switch 开关在激活状态下必定是绿色 */
.n-switch.n-switch--active .n-switch__rail {
  background-color: #18a058 !important;
}

/* ==================== 消除海报复选框未选中时的纯白底色 ==================== */
/* 1. 把未选中时的小方块变成透明，并加粗一点白色边框以便看清 */
.poster-checkbox-wrap .n-checkbox .n-checkbox-box {
  background-color: transparent !important;
  border: 1.5px solid rgba(255, 255, 255, 0.75) !important;
}

/* 2. 鼠标悬停时边框高亮 */
.poster-checkbox-wrap .n-checkbox:hover .n-checkbox-box {
  border-color: #ffffff !important;
}

/* 3. 选中时恢复正常的颜色 */
.n-checkbox.n-checkbox--checked .n-checkbox-box,
.n-checkbox.n-checkbox--indeterminate .n-checkbox-box {
  background-color: #18a058 !important;
  border-color: #18a058 !important;
}

/* 隐藏自带的白底状态遮罩层（防止悬停时闪烁白光） */
.poster-checkbox-wrap .n-checkbox .n-checkbox-box__border,
.poster-checkbox-wrap .n-checkbox .n-checkbox-box__state-border {
  display: none !important;
}

.n-space,
.n-descriptions-table-header { 
  background-color: transparent !important; 
}
</style>