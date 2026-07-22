<!-- src/App.vue -->
<template>
  <!-- 将画布使用 Teleport 挂载到 body，避免层叠上下文冲突 -->
  <Teleport to="body">
    <canvas
      v-if="isDarkTheme"
      id="starfield"
    />
  </Teleport>

  <!-- Naive UI 配置提供者 -->
  <n-config-provider 
    :theme="isDarkTheme ? darkTheme : undefined" 
    :theme-overrides="currentNaiveTheme" 
    :locale="zhCN" 
    :date-locale="dateZhCN"
  >
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

// ========== 主题与全局状态 ==========
const isDarkTheme = ref(localStorage.getItem('isDark') === 'true');

// 全局底层主题覆盖：通过 JS 变量接管 Naive UI 的核心背景与文本色，防止组件默认渲染白底
const baseThemeOverrides = {
  common: {
    textColor1: 'rgba(255, 255, 255, 0.95)',
    textColor2: 'rgba(255, 255, 255, 0.85)',
    textColor3: 'rgba(255, 255, 255, 0.65)',
    textColorDisabled: 'rgba(255, 255, 255, 0.4)',
    placeholderColor: 'rgba(255, 255, 255, 0.5)',
    placeholderColorDisabled: 'rgba(255, 255, 255, 0.3)',
    iconColor: 'rgba(255, 255, 255, 0.9)',
    popoverColor: 'transparent', // 设为透明，以便 CSS 接管实现毛玻璃效果
    modalColor: 'transparent',
    cardColor: 'transparent',
    bodyColor: 'transparent'
  }
};

// 当前生效的主题变量
const currentNaiveTheme = ref({ ...baseThemeOverrides });

// ========== 星空 Canvas 背景逻辑 ==========
let animFrameId = null;     // 保存 requestAnimationFrame 的 ID
let resizeHandler = null;   // 保存窗口尺寸变化监听函数，用于注销事件防止泄漏

/**
 * 初始化并启动星空 Canvas 动效
 */
function setupStarfield() {
  destroyStarfield(); // 初始化前先清理旧的实例

  const canvas = document.getElementById('starfield');
  if (!canvas) return;

  const ctx = canvas.getContext('2d');
  let width, height, starsArr, initialBurst = true;

  const STAR_COUNT = () => Math.floor(0.3 * width);
  const COLORS = { giant: '180,184,240', star: '226,225,142', comet: '225,225,225' };

  function randomChance(p) { return Math.random() * 1000 < p * 10; }
  function randomRange(min, max) { return Math.random() * (max - min) + min; }

  // 粒子星星类
  class Star {
    constructor() { this.reset(); }
    reset() {
      this.isGiant = randomChance(3);
      this.isComet = !this.isGiant && !initialBurst && randomChance(20);
      this.x = randomRange(0, width); 
      this.y = randomRange(0, height);
      this.size = randomRange(1.1, 2.6);
      this.dx = randomRange(0.05, 0.3) + (this.isComet ? randomRange(2.5, 6) : 0.05);
      this.dy = -randomRange(0.05, 0.3) - (this.isComet ? randomRange(2.5, 6) : 0.05);
      this.opacity = 0; 
      this.opacityTarget = randomRange(0.2, this.isComet ? 0.6 : 1);
      this.fadeSpeed = randomRange(0.0005, 0.002) + (this.isComet ? 0.001 : 0);
      this.fadingIn = true; 
      this.fadingOut = false;
    }
    fadeIn() { 
      if (this.fadingIn) { 
        this.opacity += this.fadeSpeed; 
        if (this.opacity >= this.opacityTarget) this.fadingIn = false; 
      } 
    }
    fadeOut() { 
      if (this.fadingOut) { 
        this.opacity -= this.fadeSpeed / 2; 
        if (this.opacity <= 0) this.reset(); 
      } 
    }
    move() { 
      this.x += this.dx; 
      this.y += this.dy; 
      if (!this.fadingOut && (this.x > width - width / 4 || this.y < 0)) this.fadingOut = true; 
    }
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
      ctx.closePath(); 
      ctx.fill();
    }
  }

  // 自适应调整画布大小
  function resizeCanvas() {
    width = window.innerWidth; 
    height = window.innerHeight;
    canvas.width = width; 
    canvas.height = height;
  }

  // 帧动画循环
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

  // 监听缩放事件，并保存引用以备销毁
  resizeHandler = resizeCanvas;
  window.addEventListener('resize', resizeHandler);
  init();
}

/**
 * 销毁 Canvas 星空动画与相关全局事件监听
 */
function destroyStarfield() {
  if (animFrameId) {
    cancelAnimationFrame(animFrameId);
    animFrameId = null;
  }
  if (resizeHandler) {
    window.removeEventListener('resize', resizeHandler);
    resizeHandler = null;
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

// ========== 自定义事件处理器定义 ==========
const handleThemeUpdate = (event) => {
  currentNaiveTheme.value = {
    ...baseThemeOverrides,
    ...event.detail,
    common: {
      ...baseThemeOverrides.common,
      ...(event.detail?.common || {})
    }
  };
};

const handleDarkModeUpdate = (event) => {
  isDarkTheme.value = event.detail;
};

// ========== 生命周期钩子 ==========
let appElement = null;

onMounted(() => {
  appElement = document.getElementById('app');

  if (appElement) {
    appElement.addEventListener('update-naive-theme', handleThemeUpdate);
    appElement.addEventListener('update-dark-mode', handleDarkModeUpdate);
  }

  if (isDarkTheme.value) {
    setupStarfield();
  }
});

onUnmounted(() => {
  destroyStarfield();
  if (appElement) {
    appElement.removeEventListener('update-naive-theme', handleThemeUpdate);
    appElement.removeEventListener('update-dark-mode', handleDarkModeUpdate);
  }
});
</script>

<style>
/* ==========================================================================
   1. 全局设计变量与主题 (CSS Variables)
   ========================================================================== */
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

  /* 主题卡片渐变过渡色 */
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

  /* 暗黑模式下微调的渐变 */
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

/* 强制接管 Naive UI 内部组件生成的基准 CSS 变量 */
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

/* ==========================================================================
   2. 基础容器与底层复位 (Body & Container)
   ========================================================================== */
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
  text-shadow: 0 1px 2px rgba(0, 0, 0, 0.3);
  transition: background-image 0.5s ease, color 0.3s ease;
}

/* 背景虚化与遮罩层 */
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
  display: flex; 
  justify-content: center; 
  align-items: center; 
  height: 100vh; 
  width: 100%; 
  background: transparent; 
}

/* 隐藏所有内置的全局滚动条 */
* { 
  scrollbar-width: none !important; 
  -ms-overflow-style: none !important; 
}
::-webkit-scrollbar { 
  display: none !important; 
  width: 0 !important; 
  height: 0 !important; 
}
.n-scrollbar-rail { 
  display: none !important; 
}

/* ==========================================================================
   3. 毛玻璃效果核心重写 (Cards & Panels)
   ========================================================================== */
/* 通用卡片毛玻璃化 */
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

/* 仪表盘主交互卡片 */
.n-card.dashboard-card {
  background: var(--glass-bg) !important;
  backdrop-filter: var(--glass-blur) !important;
  -webkit-backdrop-filter: var(--glass-blur) !important;
  border: none !important; /* 隐藏实体边框防止锯齿与白边 */
  box-shadow: inset 0 0 0 1px var(--glass-border), var(--glass-shadow) !important;
  color: var(--text-primary) !important;
  border-radius: 16px !important;
  transition: transform 0.2s, box-shadow 0.2s, background 0.2s !important;
  height: 100%;
  display: flex !important;
  flex-direction: column !important;
  font-size: 14px;
  background-clip: padding-box !important;
  outline: 1px solid transparent !important;
}

/* 主面板交互态悬浮 */
.n-card.dashboard-card:hover {
  background: var(--glass-bg-hover) !important;
  box-shadow: inset 0 0 0 1px var(--glass-border-light), 0 8px 24px 0 rgba(0, 0, 0, 0.2) !important;
  transform: translateY(-2px) !important;
}

/* 静态免悬浮态卡片 */
.n-card.dashboard-card.no-hover:hover {
  transform: none !important;
  box-shadow: inset 0 0 0 1px var(--glass-border), var(--glass-shadow) !important;
  background: var(--glass-bg) !important;
}

/* 卡片过渡变色样式 */
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

/* 剧集/海报专栏卡片 */
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
.card-poster-container { 
  flex-shrink: 0; 
  width: 120px !important; 
  height: 180px !important; 
  overflow: hidden; 
  border-radius: 8px; 
  box-shadow: 0 4px 12px rgba(0,0,0,0.15); 
}

/* 精简弹窗卡片背景 */
.modal-card-lite {
  background: var(--glass-bg) !important;
  backdrop-filter: var(--glass-blur) !important;
  -webkit-backdrop-filter: var(--glass-blur) !important;
  border: 1px solid var(--glass-border) !important;
  border-radius: 16px !important;
  box-shadow: var(--glass-shadow) !important;
  color: var(--text-primary) !important;
}

/* ==========================================================================
   4. 表单与交互输入类组件 (Forms & Controls)
   ========================================================================== */
/* 输入框、多选下拉框的毛玻璃复位 */
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

.n-base-selection-label,
.n-base-selection-tags {
  background-color: transparent !important;
}

/* 隐藏 Naive 原有的过渡状态实线边框（避免重合白线） */
.n-base-selection__border,
.n-base-selection__state-border,
.n-input__border,
.n-input__state-border,
.n-radio-button__state-border {
  display: none !important; 
}

.n-input__input-el, 
.n-input__placeholder,
.n-base-selection-input__content,
.n-base-selection-placeholder {
  color: rgba(255, 255, 255, 0.7) !important;
}

/* 单选按钮 (Radio Button) */
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

/* 基础交互按键适配 */
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

/* ==========================================================================
   5. 悬浮、下拉、弹窗与抽屉覆盖 (Overlay & Modals)
   ========================================================================== */
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

/* 穿透下拉选择和悬浮按钮的伪元素干扰，使其 hover 统一呈现绿色主题 */
.n-dropdown-option-body:hover::before,
.n-dropdown-option-body--pending::before,
.n-base-select-option:hover::before,
.n-base-select-option--pending::before,
.n-menu-popover .n-menu-item-content:hover::before {
  background-color: #18a058 !important;
  opacity: 1 !important;
}

/* 下拉菜单 hover 时，高亮文字与图标 */
.n-dropdown-option-body:hover .n-dropdown-option-body__label,
.n-dropdown-option-body--pending .n-dropdown-option-body__label,
.n-dropdown-option-body:hover .n-dropdown-option-body__icon,
.n-dropdown-option-body--pending .n-dropdown-option-body__icon,
.n-base-select-option:hover,
.n-base-select-option--pending {
  color: #ffffff !important;
}

/* 侧边栏折叠把手（多部分 div 拼接构成）纯白微光覆盖 */
.n-layout-toggle-bar__top,
.n-layout-toggle-bar__bottom {
  background-color: rgba(255, 255, 255, 0.5) !important;
  box-shadow: 0 0 2px rgba(255,255,255,0.9) !important;
}

.n-layout-toggle-bar:hover .n-layout-toggle-bar__top,
.n-layout-toggle-bar:hover .n-layout-toggle-bar__bottom {
  background-color: #ffffff !important;
  box-shadow: 0 0 6px rgba(255,255,255,1) !important;
  width: 3px !important;
}

/* 兜底处理侧边栏按钮图标样式 */
.n-layout-toggle-button .n-base-icon,
.n-layout-toggle-button svg,
.n-layout-toggle-button path {
  color: #ffffff !important;
  fill: #ffffff !important;
}

/* ==========================================================================
   6. 基础提示、表格及展示性组件 (Data Display)
   ========================================================================== */
/* 通用提示 (Alert) */
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

/* 徽章与标签 (Tag) */
.n-tag--default-type {
  background-color: var(--glass-bg) !important;
  color: #ffffff !important;
}
.n-tag--info-type { background-color: #2080f0 !important; }
.n-tag--success-type { background-color: #18a058 !important; }
.n-tag--warning--type { background-color: #f0a020 !important; }
.n-tag--error-type { background-color: #d03050 !important; }
.n-tag-cyan { background-color: #55ff9c1f !important; }

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
.n-text { color: var(--text-primary) !important; }

/* 基础表格 (Simple Table) */
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

/* 高级数据表格 (Data Table) */
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

.n-data-table-th__sort, 
.n-data-table-th__filter {
  color: var(--text-primary) !important;
}
.n-data-table-th__sort:hover, 
.n-data-table-th__filter:hover {
  background: rgba(255, 255, 255, 0.2) !important;
}

/* 分页器 (Pagination) */
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

.n-pagination .n-pagination-item--active {
  background: rgba(255, 255, 255, 0.2) !important;
  border-color: rgba(255, 255, 255, 0.5) !important;
  color: #ffffff !important;
  font-weight: bold;
}

.n-pagination .n-select .n-base-selection {
  background: var(--glass-bg) !important;
  border-color: var(--glass-border) !important;
}

/* 标签页 (Tabs) */
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

/* ==========================================================================
   7. 交互组件细节优化与抗闪烁微调 (Interaction Details)
   ========================================================================== */
/* 避免 transition: all 导致的色彩差值过渡错误 */
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

/* 禁用原生点击波纹扩散动效，避免形成幽灵杂色边框 */
.n-base-wave {
  display: none !important;
  animation: none !important;
}
.n-button::after,
.n-radio-button::after {
  box-shadow: none !important;
}

/* 主类型按钮（Primary）色彩兜底，确保全场景显示绿色 */
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

/* 激活状态下的开关（Switch）确保始终为绿色 */
.n-switch.n-switch--active .n-switch__rail {
  background-color: #18a058 !important;
}

/* 移除海报多选框（Checkbox）未选中时的纯白底色，提高视觉透射度 */
.poster-checkbox-wrap .n-checkbox .n-checkbox-box {
  background-color: transparent !important;
  border: 1.5px solid rgba(255, 255, 255, 0.75) !important;
}

.poster-checkbox-wrap .n-checkbox:hover .n-checkbox-box {
  border-color: #ffffff !important;
}

.n-checkbox.n-checkbox--checked .n-checkbox-box,
.n-checkbox.n-checkbox--indeterminate .n-checkbox-box {
  background-color: #18a058 !important;
  border-color: #18a058 !important;
}

/* 隐藏部分内置的状态背景层，防 Hover 过程白光闪烁 */
.poster-checkbox-wrap .n-checkbox .n-checkbox-box__border,
.poster-checkbox-wrap .n-checkbox .n-checkbox-box__state-border {
  display: none !important;
}

.n-space,
.n-descriptions-table-header { 
  background-color: transparent !important; 
}
</style>